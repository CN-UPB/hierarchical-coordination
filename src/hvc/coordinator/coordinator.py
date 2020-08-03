from pathlib import Path

import hvc.coordinator.path_computing as pc
from hvc.mip.models import InterDomainLink
from hvc.mip.utils import *

logger = logging.getLogger()
logging.basicConfig(filename='solution_interpreter.log', level=logging.DEBUG)


class Coordinator:
    """
    A coordinator is initialized with a level, the nodes (domains) and the links of its network.
    This network is a multigraph, thus there can be multiple links between the same domains.
    """

    def __init__(self, child_coordinators, name, is_root_coordinator=False, nodes=None):
        if nodes is None:
            nodes = []
            self.is_lowest_hierarchy = False
        else:
            self.is_lowest_hierarchy = True

        self.substrate_nodes = nodes
        self.substrate_subgraph = None

        self.name = name
        self.child_coordinators = child_coordinators
        self.border_nodes_in_higher_domains = defaultdict(set)

        self.inter_domain_links = []
        self.cpu_restrictions = []
        self.routing_restrictions = []
        self.intra_domain_paths = []

        self.is_root_coordinator = is_root_coordinator

    def build_hierarchy(self, network, vnf_ingresses, vnf_egresses):
        if self.is_lowest_hierarchy:
            self.substrate_subgraph = network.subgraph(self.substrate_nodes).copy()
            logger.debug("this is coordinator with name {0} nodes {1} and edges {2} ".format(self.name,
                                                                                             self.substrate_subgraph.nodes(),
                                                                                             self.substrate_subgraph.edges()))
        else:
            # first: propagate the information to all child coordinators
            for child_coordinator in self.child_coordinators:
                child_coordinator.build_hierarchy(network, vnf_ingresses, vnf_egresses)

            all_nodes_per_domain = {}
            for coordinator in self.child_coordinators:
                all_nodes_per_domain[coordinator] = coordinator.get_substrate_nodes()

            # now build the inter domain links
            for domain1, domain2 in itertools.combinations(self.child_coordinators, 2):
                counter_before = len(self.inter_domain_links)
                logger.debug("This is coordinator {0}, finding all substrate links between domains {1} and {2}."
                             " Thus, nodes {3} and {4}".format(
                    self.name, domain1, domain2, all_nodes_per_domain[domain1], all_nodes_per_domain[domain2]))

                for node_domain1, node_domain2 in itertools.product(all_nodes_per_domain[domain1],
                                                                    all_nodes_per_domain[domain2]):

                    if network.has_edge(node_domain1, node_domain2):
                        edge_data = network.get_edge_data(node_domain1, node_domain2)
                        edge_id = edge_data['id']
                        # create inter domain link
                        inter_domain_link = InterDomainLink(identifier="edge_{}".format(edge_id),
                                                            source=node_domain1, destination=node_domain2,
                                                            rate=edge_data["max_rate"], delay=edge_data["delay"])

                        domain1.set_border_node(node_domain1, domain2)
                        self.inter_domain_links.append(inter_domain_link)

                    if network.has_edge(node_domain2, node_domain1):
                        edge_data = network.get_edge_data(node_domain2, node_domain1)

                        edge_id = edge_data['id']
                        # create inter domain link
                        inter_domain_link = InterDomainLink(identifier="edge_{}".format(edge_id),
                                                            source=node_domain2, destination=node_domain1,
                                                            rate=edge_data["max_rate"], delay=edge_data["delay"])

                        domain2.set_border_node(node_domain2, domain1)
                        self.inter_domain_links.append(inter_domain_link)
                logger.debug(
                    "Found {0} links between domain {1} and {2}".format(len(self.inter_domain_links) - counter_before,
                                                                        domain1, domain2))
        substrate_nodes = self.get_substrate_nodes()
        for ingress in vnf_ingresses:
            if ingress in substrate_nodes:
                self.border_nodes_in_higher_domains["ingress"].add(ingress)

        for egress in vnf_egresses:
            if egress in substrate_nodes:
                self.border_nodes_in_higher_domains["egress"].add(egress)

    def compute_advertised_paths(self, counter=0, path_aggregation="full_expansion"):
        # top down -> let the child coordinators compute the paths first.
        if not self.is_lowest_hierarchy:
            counter = self.__compute_paths_child_coordinators(counter, path_aggregation)

        if self.is_root_coordinator:
            return

        if not self.is_lowest_hierarchy:
            self.substrate_subgraph = self.__compute_graph_from_paths()

        edge_to_path = defaultdict(list)
        node_to_path = defaultdict(list)
        intra_domain_paths = []
        path_counter = counter

        # the paths for D1 -> D2 are the same as for D2 -> D1,
        # thus compute the paths once and reverse them for the other direction

        logger.debug("This is coordinator {0}, starting to compute all the intra-domain paths.".format(self.name))
        i = 0
        ctr = 0
        for outgoing_domain, ingresses in self.border_nodes_in_higher_domains.items():
            j = 0
            for other_domain, egresses in self.border_nodes_in_higher_domains.items():
                if j <= i:
                    j += 1
                    continue
                j += 1
                ctr += 1
                logger.debug(
                    "Computing the intra-domain paths between {0} and {1}, the border nodes are {2} and {3}".format(
                        outgoing_domain, other_domain, ingresses, egresses))
                additional_paths = pc.compute_paths(substrate_subgraph=self.substrate_subgraph, ingresses=ingresses,
                                                    egresses=egresses, edge_to_path=edge_to_path,
                                                    node_to_path=node_to_path, path_counter=path_counter,
                                                    domain=self.name, is_lowest_hierarchy=self.is_lowest_hierarchy,
                                                    routing_restrictions=self.routing_restrictions)
                path_counter += len(additional_paths)
                intra_domain_path_ids = pc.get_path_subset(intra_domain_paths=additional_paths,
                                                           node_to_path=node_to_path,
                                                           edge_to_path=edge_to_path,
                                                           substrate_subgraph=self.substrate_subgraph,
                                                           is_lowest_hierarchy=self.is_lowest_hierarchy,
                                                           path_aggregation=path_aggregation
                                                           )
                old_intra_domain_paths = additional_paths
                additional_paths = [p for p in old_intra_domain_paths if p.identifier in intra_domain_path_ids]
                logger.debug("decided on the paths {}".format(intra_domain_path_ids))
                intra_domain_paths += additional_paths

            i += 1
        intra_domain_path_ids = [p.identifier for p in intra_domain_paths]
        logger.debug(
            "This is coordinator {}, i have found {} paths for {} pairs".format(self.name, len(intra_domain_path_ids),
                                                                                ctr))

        cpu_restrictions = pc.compute_cpu_restrictions(substrate_subgraph=self.substrate_subgraph,
                                                       node_to_path=node_to_path,
                                                       intra_domain_path_ids=intra_domain_path_ids,
                                                       domain=self.name,
                                                       is_lowest_hierarchy=self.is_lowest_hierarchy,
                                                       cpu_restrictions=self.cpu_restrictions,
                                                       edge_to_path=edge_to_path,
                                                       intra_domain_paths=intra_domain_paths)

        routing_restrictions = pc.compute_routing_restrictions(substrate_subgraph=self.substrate_subgraph,
                                                               edge_to_path=edge_to_path,
                                                               intra_domain_paths=intra_domain_path_ids,
                                                               domain=self.name,
                                                               old_routing_restrictions=self.routing_restrictions,
                                                               is_lowest_hierarchy=self.is_lowest_hierarchy)

        return intra_domain_paths, cpu_restrictions, routing_restrictions, path_counter

    def get_substrate_nodes(self):
        if self.is_lowest_hierarchy:
            return self.substrate_nodes
        else:
            return [node for coordinator in self.child_coordinators for node in coordinator.get_substrate_nodes()]

    def get_name(self):
        return self.name

    def __hash__(self):
        return self.name.__hash__()

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.__str__()

    def write_advertised_restriction(self, output_path):
        Path(output_path).mkdir(parents=True, exist_ok=True)
        advertised_restriction = {
            "routing_restrictions": {},
            "cpu_restrictions": {}
        }
        logger.debug("coordinator {0} has {1} rrs, and {2} crs".format(self.name, len(self.routing_restrictions),
                                                                       len(self.cpu_restrictions)))
        for routing_restriction in self.routing_restrictions:
            advertised_restriction["routing_restrictions"][
                routing_restriction.identifier] = routing_restriction.to_yaml_dict()

        for cpu_restriction in self.cpu_restrictions:
            advertised_restriction["cpu_restrictions"][cpu_restriction.identifier] = cpu_restriction.to_yaml_dict()

        with open(output_path + "/advertised_restrictions.yaml", 'w') as advertised_restriction_file:
            yaml.dump(advertised_restriction, advertised_restriction_file)

        for coordinator in self.child_coordinators:
            coordinator.write_advertised_restriction(output_path + "/" + coordinator.name)

    def write_network_description(self, output_path):
        Path(output_path).mkdir(parents=True, exist_ok=True)
        network_description = {
            "domain_nodes": {},
            key_inter_domain_edges: {},
            key_intra_domain_paths: {}
        }

        for path in self.intra_domain_paths:
            network_description[key_intra_domain_paths][path.identifier] = path.to_yaml_dict()

        if not self.is_lowest_hierarchy:
            for coordinator in self.child_coordinators:
                node_list = [node for domain in coordinator.border_nodes_in_higher_domains.values() for node in domain]
                network_description["domain_nodes"][coordinator.name] = list(set(node_list))

            for inter_domain_edge in self.inter_domain_links:
                network_description[key_inter_domain_edges][
                    inter_domain_edge.identifier] = inter_domain_edge.to_yaml_dict()

            for coordinator in self.child_coordinators:
                coordinator.write_network_description(output_path + "/" + coordinator.name)
        else:
            # each node is its own domain
            for node in self.substrate_nodes:
                network_description["domain_nodes"][node] = [node]
            for (node1, node2) in self.substrate_subgraph.edges():
                edge_attributes = self.substrate_subgraph.get_edge_data(node1, node2)
                edge_delay = edge_attributes["delay"]
                edge_rate = edge_attributes["max_rate"]
                edge_id = edge_attributes["id"]

                inter_domain_link = {
                    "src": node1, "dst": node2,
                    "max_rate": edge_rate, "delay": edge_delay
                }

                network_description[key_inter_domain_edges]["edge_" + str(edge_id)] = inter_domain_link

        with open(output_path + "/network_description.yaml", 'w+') as network_description_file:
            yaml.dump(network_description, network_description_file)

        if self.is_lowest_hierarchy:
            cpu_def = {}
            for node in self.substrate_nodes:
                cpu_def[node] = self.substrate_subgraph.nodes[node]["cpu"]
            level1_expansion(network_description_path=output_path + "/network_description.yaml", cpu_capacities=cpu_def,
                             with_backward_paths=True, overwrite=True)

    def set_border_node(self, border_node, higher_domain):
        """
        Lets a higher level hierarchy set the border nodes of this domain (as it has a better view on the network)
        """
        self.border_nodes_in_higher_domains[higher_domain].add(border_node)

        # now find out which domain this node belonged to
        for coord in self.child_coordinators:
            if border_node in coord.get_substrate_nodes():
                coord.set_border_node(border_node, higher_domain)

    def __compute_paths_child_coordinators(self, counter, aggregation):
        """
        Invokes all child coordinators to compute the advertised paths
        :param aggregation: chosses in which way to compute a path subset
        :return:
        """
        for coordinator in self.child_coordinators:
            intra_domain_paths, cpu_restrictions, routing_restrictions, inner_counter = coordinator.compute_advertised_paths(
                counter, path_aggregation=aggregation)
            counter += inner_counter
            logger.debug("child coordinator {0} yielded {1} paths, {2} rrs and {3} crs".format(coordinator.name,
                                                                                               len(intra_domain_paths),
                                                                                               len(
                                                                                                   routing_restrictions),
                                                                                               len(cpu_restrictions)))
            self.intra_domain_paths += intra_domain_paths
            self.routing_restrictions += routing_restrictions
            self.cpu_restrictions += cpu_restrictions
        return counter

    def __compute_graph_from_paths(self):
        """
        Computes an expanded network from the child coordinators paths and border nodes. this graph can, in turn,
         be used to compute paths for parent hierarchies
        :return: an networkX graph that can be used to compute the paths
        """
        # now, using these paths, build a network
        expanded_network = nx.MultiDiGraph()
        node_list = []
        for path in self.intra_domain_paths:
            if path.source not in node_list:
                expanded_network.add_node(path.source, label=path.source)
                node_list.append(path.source)

            if path.destination not in node_list:
                expanded_network.add_node(path.destination, label=path.destination)
                node_list.append(path.destination)

            expanded_network.add_edge(path.source, path.destination, key=path.identifier, label=path.identifier,
                                      max_rate=path.rate,
                                      delay=path.delay, cpu=path.cpu)

        for edge in self.inter_domain_links:
            expanded_network.add_edge(edge.source, edge.destination, key=edge.identifier, cpu=0, max_rate=edge.rate,
                                      delay=edge.delay,
                                      label=edge.identifier)

        return expanded_network

    def collect_solutions(self, output_path):
        if not os.path.isfile(output_path + "/solution.log"):
            return {}
        if self.is_lowest_hierarchy:
            with open(output_path + "/solution.log", 'r') as solution_file:
                solution = yaml.load(solution_file)
                return solution
        else:

            solutions = []
            merged_solution = defaultdict(int)

            for coordinator in self.child_coordinators:
                child_solution = coordinator.collect_solutions(
                    output_path="{0}/{1}".format(output_path, coordinator.name))
                solutions.append(coordinator.__map_solutions(child_solution, coordinator.name, output_path))

            for solution in solutions:
                for k, v in solution.items():
                    merged_solution[k] += v

            with open(output_path + "/solution.log", 'r') as solution_file:
                solution = yaml.load(solution_file)
                for k, v in solution.items():
                    if "gamma" in k and self.is_root_coordinator:
                        if "SRC" in k or "DST" in k:
                            merged_solution[k] += v
                    else:
                        if "gamma" in k:
                            continue
                        merged_solution[k] += v

            return merged_solution

    def __map_solutions(self, solution, domain_name, output_path):
        if not os.path.isfile(output_path + "/request_mappings.yaml"):
            return {}
        with open(output_path + "/request_mappings.yaml", 'r') as request_mappings_file:
            request_mappings = yaml.load(request_mappings_file, Loader=yaml.FullLoader)
            mapped_solutions = {}
            for key, value in solution.items():
                if "lambda_inter" in key:
                    # keys look like lambda_inter[(B_request2-request2,DST_request2-request2), path_11, egress_N12, edge_1]
                    first_vnf = key[key.index('(') + 1:key.index(',')]
                    second_vnf = key[key.index(',') + 1: key.index(')')]

                    request = get_request_from_arc(first_vnf)
                    vnf0 = get_vnf_from_arc(first_vnf)
                    vnf1 = get_vnf_from_arc(second_vnf)
                    trimmed_request = trim_request(request)

                    if first_vnf == "SRC_" + request:
                        corrected_first_vnf = request_mappings[domain_name][request][0]
                        first_vnf = corrected_first_vnf + "_" + trimmed_request
                    else:
                        first_vnf = vnf0 + "_" + trimmed_request
                    if second_vnf == "DST_" + request:
                        corrected_second_vnf = request_mappings[domain_name][request][1]
                        second_vnf = corrected_second_vnf + "_" + trimmed_request
                    else:
                        second_vnf = vnf1 + "_" + trimmed_request
                    corrected_key = "lambda_inter[({0},{1}){2}".format(first_vnf, second_vnf,
                                                                       key[key.index(')') + 1:])
                    if corrected_key in mapped_solutions:
                        mapped_solutions[corrected_key] += value
                    else:
                        mapped_solutions[corrected_key] = value
                if "gamma" in key:
                    if "SRC" in key and not self.is_root_coordinator:
                        continue
                    if "DST" in key and not self.is_root_coordinator:
                        continue
                    mapped_solutions[key] = value
            return mapped_solutions
