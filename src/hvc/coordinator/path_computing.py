import itertools
import operator
from collections import defaultdict

from hvc.algorithms.edmonds_karp import *
from hvc.mip import utils
from hvc.mip.models import RoutingRestriction, CpuRestriction, IntraDomainPath

logger = utils.setup_logger('pc', 'path_computing.log', logging.DEBUG)


def __get_G_from_C(C, egresses, ingresses, fixed_edge_directions):
    G = nx.Graph()
    for node in C.nodes():
        G.add_node(node, **C.nodes[node])
    edge_map = {}

    for (u, v, k) in C.edges:
        if C[u][v][k]['max_rate'] <= 0:
            logger.debug("Edge {} ({} -> {}) cannot be used anymore (dump {})".format(k, u, v, C[u][v]))
            continue
        if not G.has_edge(u, v) and not G.has_edge(v, u):
            if not (v, u) in fixed_edge_directions:
                G.add_edge(u, v, **C[u][v][k])
                fixed_edge_directions.append((u, v))
                edge_map[(u, v)] = k

    __add_super_sink(G=G, egresses=egresses, ingresses=ingresses)
    return G, edge_map, fixed_edge_directions


def __update_C_from_R(R, C, used_directions, edge_map, rate):
    for (u, v) in used_directions:

        if (u, v) not in edge_map and (v, u) not in edge_map:
            # super sink & sources
            continue

        if (v, u) in edge_map:
            # switch them
            temp = u
            u = v
            v = temp

        label = edge_map[(u, v)]
        backwards_label = utils.get_backward_edge_id(label)

        C[u][v][label]['max_rate'] = max(0, C[u][v][label]['max_rate'] - rate)
        C[v][u][backwards_label]['max_rate'] = max(0, C[v][u][backwards_label]['max_rate'] - rate)

        logger.debug("Edge {} ({} -> {}) has new max_rate {}".format(label, u, v, C[u][v][label]['max_rate']))


def __add_super_sink(G, egresses, ingresses):
    ingr_rm = []
    egr_rm = []
    for node in egresses:
        if node in ingresses:
            logger.debug("Node {} is in ingresses and egresses".format(node))
            if len(egresses) > len(ingresses):
                egr_rm.append(node)
            else:
                ingr_rm.append(node)

    for node in ingr_rm:
        ingresses.remove(node)
    for node in egr_rm:
        egresses.remove(node)

    # add super sink and super source to transform the multi source and sink problem into
    # a single source & sink problem
    G.add_node("super_ingress", cpu=0)
    G.add_node("super_egress", cpu=0)

    for egress in egresses:
        G.add_edge("super_egress", egress, max_rate=100000, delay=0, label="super_egress_edge")

    for ingress in ingresses:
        G.add_edge("super_ingress", ingress, max_rate=100000, delay=0, label="super_ingress_edge")


def __update_C_for_routing_restriction(C, routing_restrictions, bottleneck_rate, paths_in_G):
    logger.debug("Appliying restrictions for paths {} with rate {}".format(paths_in_G, bottleneck_rate))
    for routing_restriction in routing_restrictions:
        intersection = set(paths_in_G) & set(routing_restriction.paths)
        logger.debug("intersection is of {} and {} is {}".format(paths_in_G, routing_restriction.paths, intersection))
        # now check if the used path was part of the restriction
        # now deduct the bottleneck rate from all paths as the 'share' the bottleneck
        if len(intersection) >= 1:
            for p_prime in routing_restriction.paths:
                if p_prime in paths_in_G:
                    continue
                for (u, v, k) in C.edges:
                    #    logger.debug("k is {} p_prime is {} is equal {}".format(k, p_prime, (k==p_prime)))
                    if str(k) == str(p_prime):
                        C[u][v][p_prime]["max_rate"] = max(0, C[u][v][p_prime]["max_rate"] - bottleneck_rate)
                        logger.debug("Path {} has now rate {}".format(p_prime, C[u][v][p_prime]["max_rate"]))


def compute_paths(substrate_subgraph, ingresses, egresses, edge_to_path, node_to_path, path_counter, domain,
                  is_lowest_hierarchy,
                  routing_restrictions):
    """

    :param ingresses:
    :param egresses:
    :param edge_to_path:
    :param node_to_path:
    :return:
    """
    logger.info(
        "Domain {} starts to compute paths between ingresses: {} and egresses {}".format(domain, ingresses, egresses))

    # print("The graph to compute is with the following edges: {}".format(substrate_subgraph.edges))

    multigraph_eliminated = False
    intra_domain_paths = []
    fixed_edge_directions = []
    edge_map = {}

    if not is_lowest_hierarchy:
        # a graph where all the remaining capacities are denoted
        C = nx.MultiDiGraph(substrate_subgraph)

        G, edge_map, fixed_edge_directions = __get_G_from_C(C=C, egresses=egresses, ingresses=ingresses,
                                                            fixed_edge_directions=fixed_edge_directions)
        logger.debug("Graph building complete, used edge directions {}".format(fixed_edge_directions))
    else:
        G = nx.Graph(substrate_subgraph)
        __add_super_sink(G=G, egresses=egresses, ingresses=ingresses)

    while not multigraph_eliminated:
        logger.info("Starting iteration of max flow path computation... with edge_map {}".format(edge_map))
        R, paths = edmonds_karp(G=G, s="super_ingress", t="super_egress", capacity="max_rate",
                                is_lowest_hierarchy=is_lowest_hierarchy,
                                routing_restrictions=routing_restrictions)
        logger.info("Edmonds karp yielded the following paths: {}".format(paths))

        edges_to_used_rate = {}
        # iterate over all resulting paths
        for (path, flow) in paths:
            logger.debug("Starting with path {} having flow {}".format(path, flow))
            path_id = "path_{0}".format(path_counter)
            path_counter += 1
            backward_path_id = "path_{0}".format(path_counter)
            path_counter += 1
            # track total delay
            total_delay = 0
            # cpu can be tracked by a single counter as both paths will traverse the same nodes
            total_cpu = 0

            rate = flow

            used_paths = list()
            used_directions = []
            used_backward_paths = list()

            # exclude the super sink and source
            for i in range(1, len(path) - 2):
                u = path[i]
                v = path[i + 1]
                # the forward edge
                edge = G.get_edge_data(u, v)

                if not is_lowest_hierarchy:
                    backward_edge_id, edge_id = __get_edge_ids(edge_map, u, v)
                else:
                    edge_id = int(substrate_subgraph[u][v]['id'])
                    if edge_id % 2 == 0:
                        backward_edge_id = str(edge_id + 1)
                    else:
                        backward_edge_id = str(edge_id - 1)
                    edge_id = str(edge_id)
                    logger.debug("Edge & bw edge ids are: {} and {}".format(edge_id, backward_edge_id))

                used_backward_paths.append(backward_edge_id)
                used_paths.append(edge_id)
                used_directions.append((u, v))

                edge_delay = edge['delay']

                if is_lowest_hierarchy:
                    node_cpu = G.nodes[u]['cpu']
                    total_cpu += node_cpu
                else:
                    edge_cpu = edge['cpu']
                    total_cpu += edge_cpu

                total_delay += edge_delay

                if is_lowest_hierarchy:
                    edge_to_path[int(edge_id)] += [str(path_id)]
                    edge_to_path[int(backward_edge_id)] += [str(backward_path_id)]
                else:
                    # mappings for the advertised restrictions
                    edge_to_path[edge_id] += [path_id]
                    edge_to_path[backward_edge_id] += [backward_path_id]

                node_to_path[u] += [path_id, backward_path_id]

            dst = path[len(path) - 2]
            node_to_path[dst] += [path_id, backward_path_id]
            logger.debug("Resolved path {} to directions {}".format(path_id, used_directions))

            logger.debug("Path {} consists of paths {}".format(path_id, used_paths))

            if not is_lowest_hierarchy:
                logger.debug("Concluded path {}. It used the forward path ids {} and backward path ids {}".format(path,
                                                                                                                  used_paths,
                                                                                                                  used_backward_paths))
            if is_lowest_hierarchy:
                total_cpu += G.nodes[dst]["cpu"]
            else:
                __update_C_for_routing_restriction(C, routing_restrictions, rate, used_paths + used_backward_paths)
                __update_C_from_R(R, C, used_directions, edge_map, rate)

            intra_domain_path = IntraDomainPath(identifier=path_id, src=path[1], dst=dst, cpu=total_cpu,
                                                delay=total_delay, rate=rate, domain=domain)

            intra_domain_backwards_path = IntraDomainPath(identifier=backward_path_id, src=dst, dst=path[1],
                                                          cpu=total_cpu,
                                                          delay=total_delay, rate=rate, domain=domain)
            intra_domain_paths.append(intra_domain_path)
            intra_domain_paths.append(intra_domain_backwards_path)
            used_paths = []
            used_backward_paths = []

        # first step: check if there are edges which are fully congested in the current solution
        if is_lowest_hierarchy:
            multigraph_eliminated = True
        else:
            multigraph_eliminated = (len(paths) == 0)
            # multigraph_eliminated = True
            G, edge_map, fixed_edge_directions = __get_G_from_C(C=C, egresses=egresses, ingresses=ingresses,
                                                                fixed_edge_directions=fixed_edge_directions)
    return intra_domain_paths


def __get_edge_ids(edge_map, u, v):
    # now figure out which edge was used:
    if (u, v) in edge_map:
        edge_id = edge_map[u, v]
        backward_edge_id = utils.get_backward_edge_id(forward_edge_id=edge_id)
        logger.debug(
            "Edge {} ({}) was taken in the correct order it was added.".format(edge_id, (u, v)))
    else:
        # as either (v,u) or (u,v) was added and (u,v) is not in the map, (v,u) has to be in it
        backward_edge_id = edge_map[v, u]
        edge_id = utils.get_backward_edge_id(forward_edge_id=backward_edge_id)
        logger.debug("Edge {} ({}) was added as {} but used in the other direction.".format(edge_id, (u, v), (v, u)))
    return backward_edge_id, edge_id


def get_path_subset(intra_domain_paths, node_to_path, edge_to_path, substrate_subgraph, is_lowest_hierarchy,
                    path_aggregation):
    """

    :param intra_domain_paths:
    :param node_to_path:
    :param edge_to_path:
    :return:
    """
    # one_path two_paths full_expansion possible
    method = path_aggregation
    if method == "full_expansion":
        return [p.identifier for p in intra_domain_paths]

    if method == "one_path":
        conducted_pairs = []
        to_return = []
        for intra_domain_path in intra_domain_paths:
            src, dst = intra_domain_path.source, intra_domain_path.destination
            if (src, dst) in conducted_pairs or (dst, src) in conducted_pairs:
                continue
            same_paths = [p for p in intra_domain_paths if p.source == src and p.destination == dst]
            p = max(same_paths, key=operator.attrgetter('rate'))
            to_return.append(p.identifier)
            to_return.append(utils.get_backward_edge_id(p.identifier))
            conducted_pairs.append((src, dst))
        return to_return

    if method == "two_paths":
        conducted_pairs = []
        to_return = []
        for intra_domain_path in intra_domain_paths:
            src, dst = intra_domain_path.source, intra_domain_path.destination
            if (src, dst) in conducted_pairs or (dst, src) in conducted_pairs:
                continue

            same_paths = [p for p in intra_domain_paths if p.source == src and p.destination == dst]
            if len(same_paths) == 1:
                to_return.append(intra_domain_path.identifier)
                bw_pid = utils.get_backward_edge_id(intra_domain_path.identifier)
                to_return.append(bw_pid)
                conducted_pairs.append((src, dst))
                continue
            # find out which two paths have the highest combined rate
            paths_to_rate = {}
            for p, p_prime in itertools.product(same_paths, repeat=2):
                if p.identifier == p_prime.identifier:
                    continue
                if (p_prime, p) in paths_to_rate:
                    continue
                # find out which edges they share
                bottleneck_rate = p.rate + p_prime.rate
                for e, paths in edge_to_path.items():
                    if p.identifier in paths and p_prime.identifier in paths:
                        shared_bottleneck = None
                        if is_lowest_hierarchy:
                            for u, v in substrate_subgraph.edges:
                                if substrate_subgraph[u][v]['id'] == e:
                                    shared_bottleneck = substrate_subgraph[u][v]['max_rate']
                        else:
                            for u, v, k in substrate_subgraph.edges:
                                if k == e:
                                    shared_bottleneck = substrate_subgraph[u][v][e]["max_rate"]
                        bottleneck_rate = min(bottleneck_rate, shared_bottleneck)
                paths_to_rate[(p, p_prime)] = bottleneck_rate
            # get the key with the max val
            (p, p_prime) = max(paths_to_rate.items(), key=operator.itemgetter(1))[0]
            # append them to the returned paths
            to_return.append(p.identifier)
            to_return.append(utils.get_backward_edge_id(p.identifier))
            to_return.append(p_prime.identifier)
            to_return.append(utils.get_backward_edge_id(p_prime.identifier))
            conducted_pairs.append((src, dst))
        return to_return


def compute_cpu_restrictions(substrate_subgraph, node_to_path, intra_domain_path_ids, domain, is_lowest_hierarchy,
                             cpu_restrictions,
                             edge_to_path, intra_domain_paths):
    """

    :param substrate_subgraph:
    :param node_to_path:
    :param intra_domain_paths:
    :return:
    """
    logger.info("Making cr for paths {}".format(intra_domain_path_ids))

    if is_lowest_hierarchy:
        filtered_paths = defaultdict(int)
        for node, path_list in node_to_path.items():
            filtered_path_set = frozenset([path for path in path_list if path in intra_domain_path_ids])
            if len(filtered_path_set) > 1:
                shared_cpu = substrate_subgraph.nodes[node]["cpu"]
                filtered_paths[filtered_path_set] = filtered_paths[filtered_path_set] + shared_cpu

        counter = 0
        cpu_restrictions = []
        for path_list, shared_cpu in filtered_paths.items():
            cpu_restriction = CpuRestriction(identifier="cpu_restriction_{0}_{1}".format(domain, counter),
                                             paths=path_list, domain=domain, shared_cpu=shared_cpu)
            counter += 1
            cpu_restrictions.append(cpu_restriction)
        return cpu_restrictions
    else:
        new_cpu_restrictions = []
        # first replace paths in the cpu restriction with all paths that use it
        for cpu_restriction in cpu_restrictions:
            new_paths = set()
            paths_in_lower_level = cpu_restriction.paths
            for lower_level_path in paths_in_lower_level:
                # use the edge to path map to figure out which new paths use it
                for new_path in edge_to_path[lower_level_path]:
                    if new_path in intra_domain_path_ids:
                        new_paths.add(new_path)
            if len(new_paths) <= 1:
                continue
            new_cr = CpuRestriction(identifier=cpu_restriction.identifier, shared_cpu=cpu_restriction.shared_cpu,
                                    domain=domain, paths=list(new_paths))

            new_cpu_restrictions.append(new_cr)
        return new_cpu_restrictions


def compute_routing_restrictions(substrate_subgraph, edge_to_path, intra_domain_paths, domain, old_routing_restrictions,
                                 is_lowest_hierarchy):
    """
    :param substrate_subgraph:
    :param edge_to_path:
    :param intra_domain_paths:
    :return:
    """
    logger.debug("****** MAKING RR FOR DOMAIN {} (is lowest hierarchy: {}) *******".format(domain, is_lowest_hierarchy))
    if is_lowest_hierarchy:
        filtered_paths = {}
        for edge_id, path_list in edge_to_path.items():
            print("Making RR for edge {}, used by paths {}".format(edge_id, path_list))
            filtered_path_set = frozenset([path for path in path_list if path in intra_domain_paths])
            logger.debug("Filtered paths: {}".format(filtered_path_set))
            if is_lowest_hierarchy:
                edge = next(((u, v) for (u, v) in substrate_subgraph.edges() if
                             int(substrate_subgraph[u][v]['id']) == int(edge_id)),
                            None)
                if edge is None:
                    print(edge_id)
                    for edge in substrate_subgraph.edges:
                        print(edge)
                        print(substrate_subgraph[edge[0]][edge[1]]['id'])
                    print(substrate_subgraph['N5']['N3']['id']=='13')

            else:
                edge = next((u, v) for u, v in substrate_subgraph.edges() if edge_id in substrate_subgraph[u][v])

            logger.debug("Edge id {} resolves to edge {}".format(edge_id, edge))

            if len(filtered_path_set) > 1:
                if is_lowest_hierarchy:
                    print(edge)
                    shared_bottleneck = substrate_subgraph.get_edge_data(*edge)["max_rate"]
                else:
                    shared_bottleneck = substrate_subgraph[edge[0]][edge[1]][edge_id]["max_rate"]
                if filtered_path_set in filtered_paths:
                    filtered_paths[filtered_path_set] = min(filtered_paths[filtered_path_set], shared_bottleneck)
                else:
                    filtered_paths[filtered_path_set] = shared_bottleneck

        counter = 0
        routing_restrictions = []

        for path_list, shared_bottleneck in filtered_paths.items():
            routing_restriction = RoutingRestriction(identifier="routing_restriction_{0}_{1}".format(domain, counter),
                                                     paths=path_list, domain=domain,
                                                     shared_bottleneck=shared_bottleneck)
            counter += 1
            routing_restrictions.append(routing_restriction)

        return routing_restrictions
    else:
        new_routing_restrictions = []
        # first replace paths in the cpu restriction with all paths that use it
        for routing_restriction in old_routing_restrictions:
            new_paths = set()
            paths_in_lower_level = routing_restriction.paths
            for lower_level_path in paths_in_lower_level:
                # use the edge to path map to figure out which new paths use it
                for new_path in edge_to_path[lower_level_path]:
                    if new_path in intra_domain_paths:
                        new_paths.add(new_path)
            if len(new_paths) <= 1:
                continue
            new_cr = RoutingRestriction(identifier=routing_restriction.identifier,
                                        shared_bottleneck=routing_restriction.shared_bottleneck,
                                        domain=domain, paths=list(new_paths))
            new_routing_restrictions.append(new_cr)
        return new_routing_restrictions
