# noinspection PyUnresolvedReferences
from gurobipy import *

from hvc.mip.models import DecisionVariables
from hvc.mip.utils import *

logger = logging.getLogger()
logging.basicConfig(filename='solution_interpreter.log', level=logging.DEBUG)


def pretty_print_model(indices, parameters, decision_variables, domain):
    nodes_in_domain = parameters.network_description["domain_nodes"][domain]
    paths_in_domain = [path_key for path_key, path in parameters.network_description[key_intra_domain_paths].items()
                       if path["domain"] == domain]
    edges_in_domain = [edge_key for edge_key, edge in parameters.network_description[key_inter_domain_edges].items() if
                       edge["src"] in nodes_in_domain or edge["dst"] in nodes_in_domain]
    print("# ==========================================================")
    logger.debug("# ==========================================================")
    for arc, p, p_prime in itertools.product(indices.arcs, indices.paths, indices.paths):
        if p in paths_in_domain or p_prime in paths_in_domain:
            if __decision_variable_is_not_zero(decision_variables.lambda_total[arc, p, p_prime]):
                print("lambda_total[{0},{1},{2}] {3}".format(arc, p, p_prime,
                                                             decision_variables.lambda_total[arc, p, p_prime]))
                logger.debug("lambda_total[{0},{1},{2}] {3}".format(arc, p, p_prime,
                                                                    decision_variables.lambda_total[arc, p, p_prime]))
    print("# ==========================================================")
    logger.debug("# ==========================================================")

    for arc, p, p_prime, e in itertools.product(indices.arcs, indices.paths, indices.paths, edges_in_domain):
        if __decision_variable_is_not_zero(decision_variables.lambda_inter[arc, p, p_prime, e]):
            print("lambda_inter[{0},{1},{2},{3}] {4}".format(arc, p, p_prime, e,
                                                             decision_variables.lambda_inter[arc, p, p_prime, e]))
            logger.debug("lambda_inter[{0},{1},{2},{3}] {4}".format(arc, p, p_prime, e,
                                                                    decision_variables.lambda_inter[
                                                                        arc, p, p_prime, e]))
    print("# ==========================================================")
    logger.debug("# ==========================================================")

    for arc, p, p_prime, p_prime_prime in itertools.product(indices.arcs, indices.paths, indices.paths,
                                                            paths_in_domain):
        if __decision_variable_is_not_zero(decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime]):
            print("lambda_intra[{0},{1},{2},{3}] {4}".format(arc, p, p_prime, p_prime_prime,
                                                             decision_variables.lambda_intra[
                                                                 arc, p, p_prime, p_prime_prime]))
            logger.debug("lambda_intra[{0},{1},{2},{3}] {4}".format(arc, p, p_prime, p_prime_prime,
                                                                    decision_variables.lambda_intra[
                                                                        arc, p, p_prime, p_prime_prime]))


def __decision_variable_is_not_zero(variable):
    tol = 1e-5
    if variable is None:
        return False
    if isinstance(variable, Var):
        return False
    return abs(variable) >= tol


def border_node_is_ingress_for_traffic(arc, p, p_prime, decision_variables, paths_starting_at_border_node):
    """Checks whether the border node is an ingress or an egress for the traffic at an inter domain-edge"""
    if p_prime in paths_starting_at_border_node:
        return True
    for p_prime_prime in paths_starting_at_border_node:
        if __decision_variable_is_not_zero(decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime]):
            return True
    return False


def __source_generator(indices, decision_variables, edges, paths_starting_at_border_node):
    for arc, p, p_prime, e in itertools.product(indices.arcs, indices.paths, indices.paths, edges):
        while __decision_variable_is_not_zero(
                decision_variables.lambda_inter[arc, p, p_prime, e]) and border_node_is_ingress_for_traffic(arc, p,
                                                                                                            p_prime,
                                                                                                            decision_variables,
                                                                                                            paths_starting_at_border_node):
            yield (*arc, p, p_prime, e)


def __ingress_generator(parameters, indices, decision_variables, domain, border_node):
    egress_paths = ["egress_" + request['egress'] for request in parameters.vnf_requests.values() if
                    request['egress_domain'] == domain]
    for request_key, request_value in parameters.vnf_requests.items():
        ingress = request_value["ingress"]
        logger.debug("Ingress gen at request {} checks ingress {}".format(request_key, ingress))
        if ingress in border_node and request_value["ingress_domain"] == domain:
            for arc in indices.arcs:
                if get_request_from_arc(arc[0]) == request_key and "SRC" in arc[0]:
                    logger.debug("Ingress gen at node {} and arc {}".format(ingress, arc))
                    for path in (list(indices.paths) + egress_paths):
                        while __decision_variable_is_not_zero(
                                decision_variables.lambda_total[arc, "ingress_" + ingress, path]):
                            yield (*arc, path, ingress)


def __list_equal(list1, list2):
    if len(list1) != len(list2):
        return False
    for l1, l2 in zip(list1, list2):
        if l1 != l2:
            return False
    return True


def __copy_vnf_description(parameters, vnf, vnf_description):
    # add the vnf to the vnf list
    vnf_description["vnfs"].append(vnf)
    # add the rate function
    vnf_description["outgoing_rate"][vnf] = parameters.vnf_description["outgoing_rate"][vnf]
    # add the cpu consumption function
    vnf_description["cpu_consumption"][vnf] = parameters.vnf_description["cpu_consumption"][vnf]


def __define_new_service_chain(parameters, chain, output_path):
    """
    Creates a service chain in the subfolder. Therefore it copies the given specs for the chain into the
    :param chain:
    :param output_path:
    :return:
    """
    chains = {}
    chain_path = output_path + "/chains.yaml"
    # first check if there is a valid chains.yaml file already
    if os.path.isfile(chain_path):
        # load existing chains definition into dict
        with open(chain_path, 'r') as chains_file:
            chains = yaml.load(chains_file, Loader=yaml.FullLoader)

    if len(chains.keys()) > 0:
        # iterate over chains to avoid duplicates
        for chain_key, chain_val in chains.items():
            if __list_equal(chain_val, chain):
                # chain already exists -> we can safely assume that all other parameters exist as well
                return chain_key

    # no such chain defined -> define a new chain
    chain_identifier = "chain_{0}".format(len(chains.keys()))
    chains[chain_identifier] = chain

    # now we need to also make sure that the vnf descriptions are updated
    # load vnf_description file (if it exists)
    vnf_description_path = output_path + "/vnf_descriptions.yaml"
    vnf_description = {}
    if os.path.isfile(vnf_description_path):
        with open(vnf_description_path, 'r') as vnf_description_file:
            vnf_description = yaml.load(vnf_description_file, Loader=yaml.FullLoader)
    else:
        # intitialize empty dicts s.t. they can be accessed in the same manner as a loaded dict
        vnf_description["vnfs"] = []
        vnf_description["cpu_consumption"] = {}
        vnf_description["outgoing_rate"] = {}

    for (vnf1, vnf2) in chain:
        if vnf1 not in vnf_description["vnfs"]:
            __copy_vnf_description(parameters, vnf1, vnf_description)
        if vnf2 not in vnf_description["vnfs"]:
            __copy_vnf_description(parameters, vnf2, vnf_description)

    # write the files
    with open(chain_path, 'w') as chains_file, open(vnf_description_path, 'w') as vnf_description_file:
        yaml.dump(chains, chains_file)
        yaml.dump(vnf_description, vnf_description_file)

    return chain_identifier


def __define_new_request(parameters, chain, ingress, egress, initial_traffic, output_path,
                         request_identifier_prefix=""):
    # transform temporary node into normal one
    if "ingress" in ingress:
        ingress = ingress[len("ingress_"):]
    if "egress" in egress:
        egress = egress[len("egress_"):]

    if ingress == egress:
        return

    # start with the chain
    chain_identifier = __define_new_service_chain(parameters, chain, output_path)
    # now define a service request
    # load the network description of the child coordinator
    network_description_path = output_path + "/network_description.yaml"
    # this file exists (is given by assumption)
    with open(network_description_path, 'r') as network_description_file:
        network_description = yaml.load(network_description_file, Loader=yaml.FullLoader)

    # define the request
    ingress_domain = next(domain_key for domain_key, domain_value in network_description["domain_nodes"].items() if
                          ingress in domain_value)

    egress_domain = next(domain_key for domain_key, domain_value in network_description["domain_nodes"].items() if
                         egress in domain_value)

    request = {"vnf_chain": chain_identifier, "ingress": ingress, "ingress_domain": ingress_domain, "egress": egress,
               "egress_domain": egress_domain, "initial_rate": initial_traffic}

    # save the request in the vnf requests file
    vnf_requests_path = output_path + "/vnf_requests.yaml"
    vnf_requests = {}
    if os.path.isfile(vnf_requests_path):
        with open(vnf_requests_path, 'r') as vnf_requests_file:
            vnf_requests = yaml.load(vnf_requests_file, Loader=yaml.FullLoader)
            vnf_request_identifier = "{0}-request{1}".format(request_identifier_prefix, len(vnf_requests))
    else:
        if request_identifier_prefix != "":
            vnf_request_identifier = "{0}-request0".format(request_identifier_prefix)
        else:
            vnf_request_identifier = "request0"

    vnf_requests[vnf_request_identifier] = request
    # save the yaml
    with open(vnf_requests_path, 'w') as vnf_requests_file:
        yaml.dump(vnf_requests, vnf_requests_file)
    return vnf_request_identifier


def __generate_request_for_source(parameters, indices, decision_variables, paths_in_domain, border_node, arc, p,
                                  p_prime, initial_rate, model, previous_call_was_on_path=False,
                                  visited_nodes=[]):
    node_visited_before = border_node in visited_nodes and not previous_call_was_on_path
    visited_nodes = visited_nodes + [border_node]
    print(
        "DFS: Function called with arc: {0}, p:{1}, p_prime:{2} at border_node:{3} and intial_rate:{4}".format(arc, p,
                                                                                                               p_prime,
                                                                                                               border_node,
                                                                                                               initial_rate))

    # first: check for recursion stop
    # recursion stop 2: found an edge such that traffic can be routed over it
    logger.debug("Checking if there is an edge which can forward all the traffic.")
    edges_starting_at_border_node = [edge_key for edge_key, edge in
                                     parameters.network_description[key_inter_domain_edges].items() if
                                     edge["src"] == border_node]

    logger.debug("Possible edges at border node {} are {}".format(border_node, edges_starting_at_border_node))

    next_edge = next((edge for edge in edges_starting_at_border_node if __decision_variable_is_not_zero(
        decision_variables.lambda_inter[arc, p, p_prime, edge])), None)

    if next_edge is not None:
        traffic_over_edge = decision_variables.lambda_inter[arc, p, p_prime, next_edge]
        outgoing_rate = min(initial_rate, traffic_over_edge)
        logger.debug("Edge {0} will forward {1} traffic. Now finishing recursion...".format(next_edge, outgoing_rate))

        # deduct this rate from the edge
        decision_variables.lambda_inter[arc, p, p_prime, next_edge] = decision_variables.lambda_inter[
                                                                          arc, p, p_prime, next_edge] - outgoing_rate

        if (arc, p, p_prime) in decision_variables.lambda_total:

            if "ingress" in p:
                starting_node_of_arc = p[p.index("_")+1:]
            else:
                starting_node_of_arc = parameters.network_description[key_intra_domain_paths][p]["dst"]
            # check if this node was visited
            starting_node_visited = starting_node_of_arc in visited_nodes

            if starting_node_visited:
                decision_variables.lambda_total[arc, p, p_prime] = decision_variables.lambda_total[
                                                                       arc, p, p_prime] - outgoing_rate

        return outgoing_rate, border_node, []
    logger.debug("No such edge was found.")
    paths_starting_at_border_node = [path for path in paths_in_domain if
                                     parameters.network_description[key_intra_domain_paths][path][
                                         "src"] == border_node]
    logger.debug("Looking for suitable paths that can either route traffic, or, placed vnfs.")
    for path in paths_starting_at_border_node:
        # check if there is traffic going over an intra domain path (routed traffic)
        # and the previous call was not on this path (i.e. the previous call considered a placed VNF on this path)
        if not previous_call_was_on_path and __decision_variable_is_not_zero(
                decision_variables.lambda_intra[arc, p, p_prime, path]):

            if node_visited_before:
                print("Found a circle! It is using the nodes {0}".format(str(visited_nodes)))
                logger.debug("Initiating circle backoff sequence.")
                return -1, None, None

            logger.debug(
                "DFS: Found a intra-domain routing situation " +
                "(i.e. {0} traffic for arc:{1} with p:{2} and p_prime:{3} is routed over the intra dmoain path: {4}".format(
                    decision_variables.lambda_intra[arc, p, p_prime, path], arc, p, p_prime, path))

            traffic_routed_over_path = min(decision_variables.lambda_intra[arc, p, p_prime, path], initial_rate)
            next_border_node = parameters.network_description[key_intra_domain_paths][path]["dst"]
            this_is_circle_start = len(visited_nodes) == 1
            out_rate, sink, chain = __generate_request_for_source(parameters=parameters, indices=indices,
                                                                  decision_variables=decision_variables,
                                                                  paths_in_domain=paths_in_domain,
                                                                  border_node=next_border_node, arc=arc, p=p,
                                                                  p_prime=p_prime, model=model,
                                                                  initial_rate=traffic_routed_over_path,
                                                                  visited_nodes=visited_nodes)
            ### circle backoff check ###
            # out_rate -1 signals that a circle backoff has been initiated!
            if out_rate == -1:
                logger.debug("Circle backoff -> substracting {0} from the path {1}".format(initial_rate, path))
                decision_variables.lambda_intra[arc, p, p_prime, path] = decision_variables.lambda_intra[
                                                                             arc, p, p_prime, path] - initial_rate
                if __decision_variable_is_not_zero(decision_variables.lambda_intra[arc, p, p_prime, path]):
                    # the circle was only a subset of all traffic
                    paths_starting_at_border_node.append(path)
                if this_is_circle_start:
                    logger.debug("this was the start of the circle")
                    # go find another path
                    visited_paths = []
                    return -1, None, None
                else:
                    logger.debug("this was not the start of the circle!")

                    # did not find the start of the circle yet!
                    return -1, sink, chain
            ### end circle backoff check ###

            # since traffic was routed over this path & we found a src->dst path we have to make sure that this traffic
            # is not routed twice
            # out rate thereby denotes the actual rate that this path used
            decision_variables.lambda_intra[arc, p, p_prime, path] = decision_variables.lambda_intra[
                                                                         arc, p, p_prime, path] - out_rate
            return out_rate, sink, chain

        else:
            # check if there is a placement on p_prime
            # and it is not the final DST placement!
            if "DST" not in arc[1] and p_prime in paths_starting_at_border_node and __decision_variable_is_not_zero(
                    decision_variables.lambda_total[arc, p, p_prime]):
                logger.debug("DFS: Found a placement situation (i.e. path {0} starts at node {1} and rate {2} will "
                             "be placed)".format(p_prime, border_node,
                                                 decision_variables.lambda_total[arc, p, p_prime]))
                ingoing_rate = initial_rate
                # arc is of the form A->B hence the next arc is the one with B->C
                next_vnf = next(iterated_arc[1] for iterated_arc in indices.arcs if iterated_arc[0] == arc[1])
                # maximal outgoing rate on path
                vnf = get_vnf_from_arc(arc[1])
                next_arc = (arc[1], next_vnf)
                maximal_outgoing_rate_vnf = evaluate_outgoing_rate(parameters=parameters, vnf=vnf,
                                                                   ingoing_rate=ingoing_rate)

                logger.debug(
                    "DFS: Maximal outgoing rate for VNF {0} with incoming rate {1} is {2}".format(vnf, ingoing_rate,
                                                                                                  maximal_outgoing_rate_vnf))
                # as the output from the vnf computation could be split (i.e. there are multiple choices for C)
                # we have to take the minimum
                # now find a placement for the C VNF
                next_path = next(
                    iterated_path for iterated_path in indices.paths if __decision_variable_is_not_zero(
                        decision_variables.lambda_total[next_arc, p_prime, iterated_path]))

                traffic_for_next_vnf = min(maximal_outgoing_rate_vnf,
                                           decision_variables.lambda_total[next_arc, p_prime, next_path])
                next_is_this_path = False

                # consider chaining as well i.e. next_path can be p_prime
                if p_prime == next_path:
                    next_is_this_path = True
                    logger.debug(
                        "DFS: Chaining situation found! Next VNF is placed on the same path we are currently looking at")
                    next_border_node = border_node
                else:
                    # otherwise the next hop is the end of the current path
                    next_border_node = parameters.network_description[key_intra_domain_paths][p_prime]["dst"]

                logger.debug(
                    "DFS: Found next border_node:{0}, next_arc: {1}, p: {2}, p_prime: {3}, initial rate: {4}".format(
                        next_border_node,
                        next_arc,
                        p_prime,
                        next_path,
                        initial_rate))
                out_rate, sink, chain = __generate_request_for_source(parameters=parameters, indices=indices,
                                                                      decision_variables=decision_variables,
                                                                      paths_in_domain=paths_in_domain,
                                                                      border_node=next_border_node, arc=next_arc,
                                                                      p=p_prime,
                                                                      p_prime=next_path,
                                                                      initial_rate=traffic_for_next_vnf, model=model,
                                                                      previous_call_was_on_path=next_is_this_path,
                                                                      # empty visited nodes since a new arc is considered
                                                                      visited_nodes=[])

                logger.debug("Recursion finishing. This call was responsible for the placement of VNF {0}".format(vnf))
                logger.debug("Got the following result outrate {0}".format(out_rate))
                # remove the request form the arc
                arc_in_chain = (get_vnf_from_arc(next_arc[0]), get_vnf_from_arc(next_arc[1]))

                if chain is None:
                    print("Fatal error! {} {} {} {}".format(chain, sink, out_rate, next_arc))

                chain = [arc_in_chain] + chain
                # now it gets tricky
                # we have to compute the in_rate of our vnf depending on the used out_rate
                # use the relative out_rate to get the absolute in_rate (since relative in_rate mathes relative out_rate in linear functions!)
                # (only works with linear functions!)
                relative_out_rate = out_rate / decision_variables.sigma_out[vnf, p_prime]
                relative_in_rate = relative_out_rate
                absolute_in_rate = decision_variables.sigma_in[vnf, p_prime] * relative_in_rate
                logger.debug("Recursion finishing: VNF had incoming rate {0}".format(absolute_in_rate))
                # deduct it from the decision variable
                if "ingress" in p:
                    starting_node_of_arc = p[p.index("_") + 1:]
                else:
                    starting_node_of_arc = parameters.network_description[key_intra_domain_paths][p]["dst"]                # check if this node was visited
                starting_node_visited = starting_node_of_arc in visited_nodes
                if starting_node_visited:
                    decision_variables.lambda_total[arc, p, p_prime] = decision_variables.lambda_total[
                                                                           arc, p, p_prime] - absolute_in_rate

                return absolute_in_rate, sink, chain

            else:
                # recursion stop 1: egress reached
                if "DST" in arc[1] and p_prime in paths_starting_at_border_node:
                    logger.debug("DFS: Checking recursion stop 'egress' reached.")
                    if "ingress" in p:
                        starting_node_of_arc = p[p.index("_") + 1:]
                    else:
                        starting_node_of_arc = parameters.network_description[key_intra_domain_paths][p]["dst"]                    # check if this node was visited
                    starting_node_visited = starting_node_of_arc in visited_nodes
                    if starting_node_visited:
                        decision_variables.lambda_total[arc, p, p_prime] = decision_variables.lambda_total[
                                                                               arc, p, p_prime] - initial_rate
                    return initial_rate, border_node, []

    return -1, None, None


def __generate_requests_for_single_child_coordinator(parameters, indices, decision_variables, model, domain,
                                                     output_path, request_resolver):
    """
    Takes the solution of a model and parses vnf requests, vnf chains, vnf specifications for a single child coordinator
    :param parameters: the parameters of the solved model
    :param indices: the indices of the solved model
    :param decision_variables: the decision variables of the solved model
    :param model: the gurobipy model
    :param domain: the child coordinator
    :param output_path: the path of the output folder for the generated files
    :return:
    """

    # first find all border nodes of this domain
    border_nodes_in_domain = parameters.network_description["domain_nodes"][domain]
    paths_in_domain = [path_key for path_key, path in parameters.network_description[key_intra_domain_paths].items()
                       if path["domain"] == domain]

    # sources are inter domain edges ending at this border node
    # by flow conservation, we have to get rid of all traffic arriving at all border nodes
    request_resolver[domain] = {}
    list.sort(border_nodes_in_domain)

    for border_node in border_nodes_in_domain:
        inter_domain_edges_ending_at_border_node = [edge_key for edge_key, edge_description in
                                                    parameters.network_description[key_inter_domain_edges].items()
                                                    if edge_description["dst"] == border_node]
        paths_starting_at_border_node = [path for path in paths_in_domain if
                                         parameters.network_description[key_intra_domain_paths][path][
                                             "src"] == border_node]

        if "ingress" in border_node:
            logger.debug("Starting ingress gen for border node {}".format(border_node))
            gen = __ingress_generator(parameters, indices, decision_variables, domain, border_node)
            for arc0, arc1, p_prime, ingress in gen:
                gen = __ingress_generator(parameters, indices, decision_variables, domain, border_node)
                logger.debug("Ingress found {}".format(ingress))
                arc = (arc0, arc1)
                p = border_node
                initial_rate = decision_variables.lambda_total[arc, p, p_prime]
                out_rate, sink, chain = __generate_request_for_source(parameters, indices, decision_variables,
                                                                      paths_in_domain,
                                                                      ingress, arc, p, p_prime, initial_rate, model)
                if out_rate == -1:
                    # circle was found!
                    print("Circle was found and eliminated. Continuing...")
                    print("Updated model: ")
                    pretty_print_model(indices=indices, decision_variables=decision_variables, parameters=parameters,
                                       domain=domain)

                    continue

                chain = [("SRC", get_vnf_from_arc(arc[1]))] + chain

                # ultimately replace the final vnf with DST
                final_arc = chain[-1]
                final_arc_replaced = (final_arc[0], "DST")
                chain[-1] = final_arc_replaced

                request_prefix = get_request_from_arc(arc0)

                # chain = chain + [(chain[-1][1], "DST")]
                request_identifier = __define_new_request(parameters=parameters, chain=chain,
                                                          initial_traffic=out_rate,
                                                          output_path=output_path, ingress=border_node, egress=sink,
                                                          request_identifier_prefix=request_prefix)

                request_resolver[domain][request_identifier] = (get_vnf_from_arc(arc[0]), final_arc[1])

                print("Found path from {0} to {1} using chain {2} and intial_rate {3}.\nIt has identifier {4}".format(
                    border_node, sink, chain,
                    out_rate, request_identifier))
                logger.debug(
                    "Found path from {0} to {1} using chain {2} and intial_rate {3}.\nIt has identifier {4}".format(
                        border_node, sink, chain,
                        out_rate, request_identifier))
                print("Updated model: ")
                pretty_print_model(indices=indices, decision_variables=decision_variables, parameters=parameters,
                                   domain=domain)

        # figure out what traffic was still not yet distributed
        if len(inter_domain_edges_ending_at_border_node) > 0:
            # this is a source in the domain as it is an incoming inter-domain edge
            # as all inter domain edges are invisible to the lower level domain, treat the edge destination as a source
            source_gen = __source_generator(indices, decision_variables, inter_domain_edges_ending_at_border_node,
                                            paths_starting_at_border_node)
            for arc0, arc1, p, p_prime, e in source_gen:
                arc = (arc0, arc1)
                initial_rate = decision_variables.lambda_inter[arc, p, p_prime, e]
                logger.debug("Chose lambda_inter[({}{}),{},{},{}] = {}".format(arc0, arc1, p, p_prime, e, initial_rate))

                # invoke the recursive DFS which will figure out a sink based on the model
                out_rate, sink, chain = __generate_request_for_source(parameters, indices, decision_variables,
                                                                      paths_in_domain,
                                                                      border_node, arc, p, p_prime, initial_rate,
                                                                      model)
                if out_rate == -1:
                    # circle was found!
                    decision_variables.lambda_inter[arc, p, p_prime, e] = decision_variables.lambda_inter[
                                                                              arc, p, p_prime, e] - initial_rate
                    logger.debug("Circle was found and eliminated. Continuing...")
                    print("Updated model: ")
                    logger.debug("Updated model: ")
                    pretty_print_model(indices=indices, decision_variables=decision_variables, parameters=parameters,
                                       domain=domain)
                    continue

                # deduct it from e
                # (the sink may not recevie all traffic!)
                decision_variables.lambda_inter[arc, p, p_prime, e] = decision_variables.lambda_inter[
                                                                          arc, p, p_prime, e] - out_rate

                # this DFS path is now a request in the lower domain

                chain = [("SRC", get_vnf_from_arc(arc[1]))] + chain

                # ultimately replace the final vnf with DST
                final_arc = chain[-1]
                final_arc_replaced = (final_arc[0], "DST")
                chain[-1] = final_arc_replaced

                request_prefix = get_request_from_arc(arc0)

                request_identifier = __define_new_request(parameters=parameters, chain=chain,
                                                          initial_traffic=out_rate,
                                                          output_path=output_path, ingress=border_node, egress=sink,
                                                          request_identifier_prefix=request_prefix)

                request_resolver[domain][request_identifier] = (get_vnf_from_arc(arc[0]), final_arc[1])

                print("Found path from {0} to {1} using chain {2} and intial_rate {3}.\nIt has identifier {4}".format(
                    border_node, sink, chain,
                    out_rate, request_identifier))
                logger.debug(
                    "Found path from {0} to {1} using chain {2} and intial_rate {3}.\nIt has identifier {4}".format(
                        border_node, sink, chain,
                        out_rate, request_identifier))
                print("Updated model: ")
                logger.debug("Updated model: ")
                pretty_print_model(indices=indices, decision_variables=decision_variables, parameters=parameters,
                                   domain=domain)
    return request_resolver


def __get_dec_vars_for_domain(parameters, indices, decision_variables, model, domain):
    nodes_in_domain = parameters.network_description["domain_nodes"][domain]
    ingress_paths__in_domain = ["ingress_" + request_value['ingress'] for request_value in
                                parameters.vnf_requests.values() if request_value['ingress_domain'] == domain]
    egress_paths__in_domain = ["egress_" + request_value['egress'] for request_value in parameters.vnf_requests.values()
                               if request_value['egress_domain'] == domain]

    paths_in_domain = [path_key for path_key, path in parameters.network_description[key_intra_domain_paths].items()
                       if path["domain"] == domain] + ingress_paths__in_domain + egress_paths__in_domain
    edges_in_domain = [edge_key for edge_key, edge in parameters.network_description[key_inter_domain_edges].items() if
                       edge["src"] in nodes_in_domain or edge["dst"] in nodes_in_domain]
    lambda_total = {}
    lambda_intra = {}
    lambda_inter = {}
    sigma_out = {}
    sigma_in = {}
    zeta = {}
    for arc, p, p_prime in itertools.product(indices.arcs, indices.paths, indices.paths):
        if p in paths_in_domain or p_prime in paths_in_domain:
            lambda_total[arc, p, p_prime] = decision_variables.lambda_total[arc, p, p_prime].X
        for p_prime_prime in paths_in_domain:
            lambda_intra[arc, p, p_prime, p_prime_prime] = decision_variables.lambda_intra[
                arc, p, p_prime, p_prime_prime].X
        for e in edges_in_domain:
            lambda_inter[arc, p, p_prime, e] = decision_variables.lambda_inter[arc, p, p_prime, e].X
        for b in nodes_in_domain:
            # zeta[arc, p, p_prime, b] = decision_variables.zeta[arc, p, p_prime, b]
            pass

    for vnf, path in itertools.product(indices.vnfs, paths_in_domain):
        sigma_in[vnf, path] = decision_variables.sigma_in[vnf, path].X
        sigma_out[vnf, path] = decision_variables.sigma_out[vnf, path].X

    return DecisionVariables(lambda_total=lambda_total, lambda_inter=lambda_inter, lambda_intra=lambda_intra,
                             sigma_in=sigma_in, sigma_out=sigma_out,
                             delta_inter=decision_variables.delta_inter,
                             delta_intra=decision_variables.delta_intra,
                             gamma=decision_variables.gamma,
                             kappa=decision_variables.kappa, beta=decision_variables.beta,
                             epsilon=decision_variables.epsilon,
                             zeta=zeta)


def generate_requests_for_child_coordinators(parameters, indices, decision_variables, model, path_prefix=""):
    """
    Takes the solution of a model and parses vnf requests, vnf chains, vnf specifications for the child coordinators
    :param path_prefix: the prefix of the output path where the domains are placed
    :param parameters: the parameters of the solved model
    :param indices: the indices of the solved model
    :param decision_variables: the decision variables of the solved model
    :param model: the gurobipy model
    :return:
    """
    request_resolver = {}
    domains = parameters.network_description["domain_nodes"].keys()
    for domain in domains:
        print("****************DOMAIN {0}*******************".format(domain))
        logger.debug("****************DOMAIN {0}*******************".format(domain))
        dec_vars_model = __get_dec_vars_for_domain(parameters, indices, decision_variables, model, domain)
        pretty_print_model(indices=indices, decision_variables=dec_vars_model, parameters=parameters,
                           domain=domain)
        domain_path = path_prefix + str(domain)
        if not os.path.exists(domain_path):
            os.mkdir(domain_path)
        # delete the exisiting requests...
        if os.path.exists(path_prefix + str(domain) + "/vnf_requests.yaml"):
            os.remove(path_prefix + str(domain) + "/vnf_requests.yaml")
        if os.path.exists(path_prefix + str(domain) + "/chains.yaml"):
            os.remove(path_prefix + str(domain) + "/chains.yaml")
        if os.path.exists(path_prefix + str(domain) + "/vnf_descriptions.yaml"):
            os.remove(path_prefix + str(domain) + "/vnf_descriptions.yaml")

        __generate_requests_for_single_child_coordinator(parameters, indices, dec_vars_model, model, domain,
                                                         path_prefix + str(domain), request_resolver)

    with open(path_prefix + "request_mappings.yaml", 'w+') as request_mapping_file:
        yaml.dump(request_resolver, request_mapping_file)
