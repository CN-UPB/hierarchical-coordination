# noinspection PyUnresolvedReferences
from gurobipy import *

from hvc.mip.models import *
from hvc.mip.utils import *

bigM = 1e5
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


def __add_backward_edges(parameters):
    """
    All edges and paths are useable in a backward manner
    :param inter_domain_edges:
    :param intra_domain_paths:
    :param cpu_restrictions:
    :param routing_restrictions:
    :return:
    """
    inter_domain_edges = parameters.network_description[key_inter_domain_edges]
    intra_domain_paths = parameters.network_description[key_intra_domain_paths]
    routing_restrictions_edges = {}
    routing_restrictions_paths = parameters.advertised_restrictions[key_routing_restrictions]
    cpu_restrictions = parameters.advertised_restrictions[key_cpu_restrictions]

    if routing_restrictions_paths is None:
        routing_restrictions_paths = {}
        parameters.advertised_restrictions[key_routing_restrictions] = routing_restrictions_paths

    if routing_restrictions_edges is None:
        routing_restrictions_edges = {}

    if cpu_restrictions is None:
        cpu_restrictions = {}
        parameters.advertised_restrictions[key_cpu_restrictions] = cpu_restrictions
    # do not add to collections while iterating over them
    edges_to_add = {}
    paths_to_add = {}

    for edge_identifier, edge in inter_domain_edges.items():
        backward_identifier = str(edge_identifier) + "_backward"
        backward_edge = dict(edge)
        backward_edge["src"] = edge["dst"]
        backward_edge["dst"] = edge["src"]
        edges_to_add[backward_identifier] = backward_edge
        routing_restriction_key = "routing_" + str(edge_identifier) + "_" + str(backward_identifier)
        routing_restrictions_edges[routing_restriction_key] = {
            "edges": [edge_identifier, backward_identifier],
            "shared_bottleneck": edge["max_rate"]
        }
    inter_domain_edges.update(edges_to_add)

    for path_identifier, path in intra_domain_paths.items():
        backward_identifier = str(path_identifier) + "_backward"
        backward_path = dict(path)
        backward_path["src"] = path["dst"]
        backward_path["dst"] = path["src"]
        paths_to_add[backward_identifier] = backward_path
        for routing_restriction in routing_restrictions_paths.values():
            if path_identifier in routing_restriction["paths"]:
                routing_restriction["paths"].append(backward_identifier)

        routing_restriction_key = "routing_" + str(path_identifier) + "_" + str(backward_identifier)
        routing_restrictions_paths[routing_restriction_key] = {
            "domain": path["domain"],
            "paths": [path_identifier, backward_identifier],
            "shared_bottleneck": path["max_rate"]
        }

        cpu_restriction_key = "cpu_" + str(path_identifier) + "_" + str(backward_identifier)
        cpu_restrictions[cpu_restriction_key] = {
            "domain": path["domain"],
            "paths": [path_identifier, backward_identifier],
            "shared_cpu": path["cpu"]
        }
    intra_domain_paths.update(paths_to_add)
    parameters.advertised_restrictions["routing_restriction_edges"] = routing_restrictions_edges


def __add_temporary_nodes_and_paths(parameters, indices):
    """
    Adds the intermediate ingress/egress paths to the model. On these paths the SRC and DST VNFs are being placed.
    :param parameters the parameter description of the model, including the network description and the vnf_requests
    :return:
    """
    network_description = parameters.network_description
    vnf_requests = parameters.vnf_requests
    domain_nodes = network_description["domain_nodes"]
    intra_domain_paths = network_description["intra_domain_paths"]
    for request in vnf_requests.values():
        ingress_domain = request["ingress_domain"]
        egress_domain = request["egress_domain"]
        ingress_node_key = "ingress_" + str(request["ingress"])
        egress_node_key = "egress_" + str(request["egress"])

        if ingress_node_key not in indices.border_nodes:
            indices.border_nodes.append(ingress_node_key)

        if egress_node_key not in indices.border_nodes:
            indices.border_nodes.append(egress_node_key)

        print(domain_nodes)

        # only add a path if there is none (i.e. if the source is responsible for multiple requests only one dummy edge)
        if ingress_node_key not in domain_nodes[ingress_domain]:
            intra_domain_paths[ingress_node_key] = {
                "domain": ingress_domain, "src": ingress_node_key, "dst": request["ingress"], "max_rate": "1000000",
                "delay": 0, "cpu": 0
            }
            domain_nodes[ingress_domain].append(ingress_node_key)
        # likewise for egress domain
        if egress_node_key not in domain_nodes[egress_domain]:
            intra_domain_paths[egress_node_key] = {
                "domain": egress_domain, "src": request["egress"], "dst": egress_node_key, "max_rate": "1000000",
                "delay": 0, "cpu": 0
            }
            domain_nodes[egress_domain].append(egress_node_key)


def __load_descriptions(network_description_file, vnf_description_file, chain_description_file,
                        vnf_request_description_file, advertised_restriction_file):
    with open(network_description_file, 'r') as network_description_file, open(vnf_description_file,
                                                                               'r') as vnf_description_file, open(
        chain_description_file, 'r') as chain_description_file, open(
        vnf_request_description_file) as vnf_request_description_file, open(
        advertised_restriction_file) as advertised_restriction_file:
        # Parse from yaml files to dicts
        network_description = yaml.safe_load(network_description_file)
        vnf_requests = yaml.safe_load(vnf_request_description_file)
        chains = yaml.load(chain_description_file, Loader=yaml.FullLoader)
        vnf_description = yaml.safe_load(vnf_description_file)
        advertised_restrictions = yaml.safe_load(advertised_restriction_file)

    return Parameters(network_description=network_description, vnf_description=vnf_description, chains=chains,
                      vnf_requests=vnf_requests, advertised_restrictions=advertised_restrictions)


def __define_indices(parameters):
    arcs = [(arc[0] + "_" + request_key, arc[1] + "_" + request_key) for request_key, request_value in
            parameters.vnf_requests.items()
            for arc in parameters.chains[request_value["vnf_chain"]]]
    if parameters.advertised_restrictions["cpu_restrictions"] is not None:
        cpu_restrictions = parameters.advertised_restrictions["cpu_restrictions"].keys()
    else:
        cpu_restrictions = []

    if parameters.network_description[key_intra_domain_paths] is not None:
        paths = parameters.network_description[key_intra_domain_paths].keys()
    else:
        paths = {}

    if parameters.network_description[key_inter_domain_edges].keys() is not None:
        edges = parameters.network_description[key_inter_domain_edges].keys()
    else:
        edges = {}

    vnfs = parameters.vnf_description["vnfs"]
    border_nodes = [node for nodeList in parameters.network_description["domain_nodes"].values() for node in
                    nodeList]
    if parameters.advertised_restrictions["routing_restrictions"] is not None:
        routing_restrictions = parameters.advertised_restrictions["routing_restrictions"].keys()
    else:
        routing_restrictions = []
    return Indices(cpu_restrictions=cpu_restrictions, paths=paths, edges=edges, vnfs=vnfs,
                   border_nodes=border_nodes,
                   arcs=arcs, routing_restrictions=routing_restrictions)


def __define_decision_variables(parameters, indices, model):
    # A->B,p,p':
    # A placed on p, B placed on p' then lambda total is the total traffic from A to B
    lambda_total = model.addVars(itertools.product(indices.arcs, indices.paths, indices.paths), lb=0,
                                 name="lambda_total")
    # A->B,p,p',e:
    # A placed on p, B placed on p' then lambda_inter is the traffic from A->B that is routed over edge e
    lambda_inter = model.addVars(itertools.product(indices.arcs, indices.paths, indices.paths, indices.edges), lb=0,
                                 name="lambda_inter")

    # A->B,p,p',p'':
    # A placed on p, B placed on p' then lambda_intra is the traffic from A->B that is routed over path p''
    lambda_intra = model.addVars(itertools.product(indices.arcs, indices.paths, indices.paths, indices.paths), lb=0,
                                 name="lambda_intra")

    # total incoming rate of a VNF placed on path
    sigma_in = model.addVars(itertools.product(indices.vnfs, indices.paths), lb=0, name="sigma_in")

    # total outgoing rate of a VNF placed on path
    sigma_out = model.addVars(itertools.product(indices.vnfs, indices.paths), lb=0, name="sigma_out")

    # 0/1 if edge is used
    delta_inter = model.addVars(itertools.product(indices.arcs, indices.paths, indices.paths, indices.edges),
                                vtype=GRB.BINARY,
                                name="delta_inter")

    # 0/1 if path is used
    delta_intra = model.addVars(itertools.product(indices.arcs, indices.paths, indices.paths, indices.paths),
                                vtype=GRB.BINARY,
                                name="delta_intra")

    # 0/1 if vnf is placed on path
    gamma = model.addVars(itertools.product(indices.vnfs, indices.paths), vtype=GRB.BINARY, name="gamma")

    # Cpu demands
    kappa = model.addVars(itertools.product(indices.vnfs, indices.paths), vtype=GRB.INTEGER, lb=0, name="kappa")

    # rate of the path
    beta = model.addVars(indices.paths, lb=0, name="beta")

    # Denote the shared cpu
    epsilon = model.addVars(itertools.product(indices.cpu_restrictions, indices.paths), lb=0, name="epsilon")

    # denotes the max delay
    zeta = model.addVars(itertools.product(indices.arcs, indices.paths, indices.paths, indices.border_nodes), lb=0,
                         name="zeta")

    return DecisionVariables(lambda_total=lambda_total, lambda_inter=lambda_inter, lambda_intra=lambda_intra,
                             sigma_in=sigma_in, sigma_out=sigma_out,
                             delta_inter=delta_inter,
                             delta_intra=delta_intra,
                             gamma=gamma, kappa=kappa, beta=beta, epsilon=epsilon, zeta=zeta)


# Restriction rules
# 1. Outgoing rate depends on incoming rate
def __outrate_constraint(parameters, indices, decision_variables, model):
    for vnf, path in itertools.product(indices.vnfs, indices.paths):
        model.addConstr(
            decision_variables.sigma_out[vnf, path] == evaluate_outgoing_rate(parameters=parameters, vnf=vnf,
                                                                              ingoing_rate=
                                                                              decision_variables.sigma_in[
                                                                                  vnf, path]),
            name="outrate_" + vnf + "_" + path)


# 2. cpu demand depends on incoming rate
def __cpu_consumption_constraint(parameters, indices, decision_variables, model):
    for vnf, path in itertools.product(indices.vnfs, indices.paths):
        model.addConstr(
            decision_variables.kappa[vnf, path] >= evaluate_cpu_consumption(parameters=parameters, vnf=vnf,
                                                                            ingoing_rate=
                                                                            decision_variables.sigma_in[
                                                                                vnf, path]),
            name="cpu_consumption_" + vnf + "_" + path)


# 3. inter domain edges capacity constraint
def __inter_domain_edge_capacity_constraint(parameters, indices, decision_variables, model):
    for edge in indices.edges:
        # all routed traffic over a link must not exceed the links capacity
        model.addConstr(quicksum(
            decision_variables.lambda_inter[alpha, p, p_prime, edge] for alpha in indices.arcs for p in
            indices.paths
            for p_prime in indices.paths) <= get_rate_of_link(parameters=parameters, link=edge),
                        name="inter_domain_capacity_" + edge)


# 4. Big-M inter domain edges
def __bigM_inter_domain_edge_constraint(parameters, indices, decision_variables, model):
    for arc, p, p_prime, edge in itertools.product(indices.arcs, indices.paths, indices.paths, indices.edges):
        model.addConstr(
            decision_variables.lambda_inter[arc, p, p_prime, edge] <= bigM * decision_variables.delta_inter[
                arc, p, p_prime, edge],
            name="bigM_interdomain_edges_" + str(arc) + "_" + p + "_" + p_prime + "_" + edge)


# 5. Big-M intra domain edges
def __bigM_intra_domain_path_constraint(parameters, indices, decision_variables, model):
    for arc, p, p_prime, p_prime_prime in itertools.product(indices.arcs, indices.paths, indices.paths,
                                                            indices.paths):
        model.addConstr(
            decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime] <= bigM *
            decision_variables.delta_intra[
                arc, p, p_prime, p_prime_prime],
            name="bigM_intradomain_paths_" + str(arc) + "_" + p + "_" + p_prime + "_" + p_prime_prime)


# 6 Big-M placement
def __bigM_placement_constraint(parameters, indices, decision_variables, model):
    for vnf, path in itertools.product(indices.vnfs, indices.paths):
        model.addConstr(decision_variables.sigma_in[vnf, path] <= bigM * decision_variables.gamma[vnf, path])


# 7. outrate of component is distrbuted
def __outrate_distribution_constraint(parameters, indices, decision_variables, model):
    for vnf, path in itertools.product(indices.vnfs, indices.paths):
        arcs_starting_with_vnf = [arc for arc in indices.arcs if vnf == get_vnf_from_arc(arc[0])]
        if len(arcs_starting_with_vnf) > 0:
            # all the outgoing traffic of a VNF has to be distributed among requests
            model.addConstr(decision_variables.sigma_out[vnf, path] == quicksum(
                decision_variables.lambda_total[arc, path, p_prime] for arc in arcs_starting_with_vnf for p_prime in
                indices.paths),
                            name="outrate_distribution_" + vnf + "_" + path)


# 8. Inrate distribution
def __inrate_distribution_constraint(parameters, indices, decision_variables, model):
    for vnf, path in itertools.product(indices.vnfs, indices.paths):
        arcs_ending_with_vnf = [arc for arc in indices.arcs if vnf == get_vnf_from_arc(arc[1])]
        if len(arcs_ending_with_vnf) > 0:
            # all incoming traffic of a VNF has to come from requests
            model.addConstr(decision_variables.sigma_in[vnf, path] == quicksum(
                decision_variables.lambda_total[arc, p_prime, path] for arc in arcs_ending_with_vnf for p_prime in
                indices.paths),
                            name="inrate_distribution" + vnf + "_" + path)


# 9. CPU constraint
def __cpu_capacity_constraint(parameters, indices, decision_variables, model):
    for path in indices.paths:
        exclusive_cpu = get_cpu_of_path(parameters=parameters, path=path) - quicksum(
            parameters.advertised_restrictions["cpu_restrictions"][constraint_key]["shared_cpu"] for constraint_key
            in indices.cpu_restrictions if
            path in parameters.advertised_restrictions["cpu_restrictions"][constraint_key]["paths"])

        model.addConstr(
            quicksum(decision_variables.kappa[vnf, path] for vnf in indices.vnfs) <= exclusive_cpu + quicksum(
                decision_variables.epsilon[cpu_restriction, path] for cpu_restriction in indices.cpu_restrictions),
            name="cpu_max_cap_" + path)


# 10. advertised cpu constraint
def __advertised_cpu_capacity_constraint(parameters, indices, decision_variables, model):
    for cpu_restriction in indices.cpu_restrictions:
        paths_in_restriction = parameters.advertised_restrictions["cpu_restrictions"][cpu_restriction]["paths"]
        shared_cpu = parameters.advertised_restrictions["cpu_restrictions"][cpu_restriction]["shared_cpu"]
        model.addConstr(quicksum(decision_variables.epsilon[cpu_restriction, path] for path in
                                 paths_in_restriction) <= \
                        shared_cpu, name="cpu_advertised_cap_" + cpu_restriction)


# 11. max delay constraint for a request
def __max_delay_request_constraint(parameters, indices, decision_variables, model):
    """
    DEPRECATED: the max delay assumption has been dropped as this calculation was inprecise
    :param parameters:
    :param indices:
    :param decision_variables:
    :param model:
    :return:
    """
    for request_key, request in parameters.vnf_requests.items():
        final_arc = next(arc for arc in indices.arcs if arc[1] == "DST_" + request_key)
        print(request["max_delay"])
        egress = request["egress"]
        for p in indices.paths:
            if "ingress" not in p and "egress" not in p:
                model.addConstr(decision_variables.zeta[final_arc, p, "egress_" + egress, egress] <= request[
                    "max_delay"])
    #  all_zetas = [decision_variables.zeta[final_arc, p, "egress_"+request["egress"], request["egress"]] for p in indices.paths]
    # model.addConstr(final_arc == max_(all_zetas))
    #  model.addConstr(final_arc <= request["max_delay"], name="max_delay_request_" + str(request_key))


# 12. flow conservation at VNF ingresses/egresses
def __ingress_placement_constraint(parameters, indices, decision_variables, model):
    for request_key, request in parameters.vnf_requests.items():
        intra_domain_paths = parameters.network_description[key_intra_domain_paths]
        request = parameters.vnf_requests[request_key]
        ingress_node = request["ingress"]
        # place SRC into the v_ingress -> v_path and DST into v -> v_egress
        # search for path with v_ingress as source and v as dst
        for path_key, path_value in intra_domain_paths.items():
            if path_value["src"] == "ingress_" + str(ingress_node) and path_value["dst"] == ingress_node:
                model.addConstr(decision_variables.gamma["SRC", path_key] == 1,
                                name="ingress_placement_" + request_key)


# 13. flow conservation at sources, sources have initial rate
def __ingress_initial_rate_constraint(parameters, indices, decision_variables, model):
    for request_key, request in parameters.vnf_requests.items():
        initial_rate = request['initial_rate']
        ingress = request['ingress']
        ingress_path = "ingress_" + str(ingress)
        model.addConstr(quicksum(
            decision_variables.lambda_total[arc, ingress_path, p] for arc in indices.arcs for p in
            indices.paths if get_request_from_arc(arc[0]) == request_key and get_vnf_from_arc(
                arc[0]) == "SRC" and p != ingress_path) == initial_rate,
                        name="ingress_initial_rate_{}".format(request_key))


# 14. flow conservation at egress: place DST at egress path
def __egress_placement_constraint(parameters, indices, decision_variables, model):
    for request_key, request in parameters.vnf_requests.items():
        intra_domain_paths = parameters.network_description[key_intra_domain_paths]
        egress_node = request["egress"]
        # place SRC into the v_ingress -> v_path and DST into v -> v_egress
        # search for path with v_ingress as source and v as dst
        for path_key, path_value in intra_domain_paths.items():
            if path_value["dst"] == "egress_" + str(egress_node) and path_value["src"] == egress_node:
                model.addConstr(decision_variables.gamma["DST", path_key] == 1,
                                name="egress_placement_" + request_key)


# 15. flow conservation at egress: DST has total rate as receiving
def __egress_final_rate_constraint(parameters, indices, decision_variables, model):
    for request_key, request in parameters.vnf_requests.items():
        egress = request['egress']
        # first compute the final rate
        ingoing_rate = request["initial_rate"]
        egress_path = "egress_" + str(egress)
        # calculate outgoing rate
        outgoing_rate = ingoing_rate
        for tup in parameters.chains[request["vnf_chain"]]:
            outgoing_rate = evaluate_outgoing_rate(parameters=parameters, vnf=tup[1],
                                                   ingoing_rate=outgoing_rate)

        model.addConstr(quicksum(
            decision_variables.lambda_total[arc, p, egress_path] for arc in indices.arcs for p in indices.paths if
            get_request_from_arc(arc[0]) == request_key and get_vnf_from_arc(
                arc[1]) == "DST" and p != egress_path) == outgoing_rate, name="egress_final_rate_" + request_key)


# 16. flow conservation at border nodes
def __flow_conservation_border_nodes_constraint(parameters, indices, decision_variables, model):
    for border_node, arc, p, p_prime in itertools.product(indices.border_nodes, indices.arcs, indices.paths,
                                                          indices.paths):
        # some restriction filtering
        #   if ("SRC" in arc[0] and "ingress" not in p) or ("DST" in arc[1] and "egress" not in p_prime):
        #       continue

        intra_domain_paths = parameters.network_description[key_intra_domain_paths]
        inter_domain_edges = parameters.network_description[key_inter_domain_edges]
        # do not route traffic if p = p_prime (there is no such traffic),
        # do not bother with border nodes
        # do not route traffic if we are the intial source of the traffic or the destination of the traffic
        if p != p_prime and "ingress" not in border_node and "egress" not in border_node and border_node != \
                intra_domain_paths[p]["dst"] and border_node != intra_domain_paths[p_prime]["src"]:
            paths_starting_at_border_node = [path_key for path_key, path_value in intra_domain_paths.items() if
                                             path_value["src"] == border_node]
            paths_ending_at_border_node = [path_key for path_key, path_value in intra_domain_paths.items() if
                                           path_value["dst"] == border_node]
            edges_starting_at_border_node = [edge_key for edge_key, edge_value in inter_domain_edges.items() if
                                             edge_value["src"] == border_node]
            edges_ending_at_border_node = [edge_key for edge_key, edge_value in inter_domain_edges.items() if
                                           edge_value["dst"] == border_node]
            model.addConstr(
                quicksum(
                    decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime] for p_prime_prime in
                    paths_ending_at_border_node if p_prime_prime != p and p_prime_prime != p_prime)
                +
                quicksum(decision_variables.lambda_inter[arc, p, p_prime, e] for e in
                         edges_ending_at_border_node)
                ==
                quicksum(
                    decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime] for p_prime_prime in
                    paths_starting_at_border_node if p_prime_prime != p and p_prime_prime != p_prime)
                +
                quicksum(decision_variables.lambda_inter[arc, p, p_prime, e] for e in
                         edges_starting_at_border_node),
                name="flow_conservation_" + border_node + "_" + str(arc) + "_" + p + "_" + p_prime)


# 17. beta definition for paths
def __max_rate_def_constraint(parameters, indices, decision_variables, model):
    for p in indices.paths:
        intra_domain_paths = parameters.network_description[key_intra_domain_paths]
        decision_vars = []
        paths_different_from_p = [path for path in intra_domain_paths if path != p]
        for request_key, request in parameters.vnf_requests.items():
            vnf_chain = [(arc[0] + "_" + request_key, arc[1] + "_" + request_key) for arc in
                         parameters.chains[request["vnf_chain"]]]
            boxes = []
            for index, pair in enumerate(vnf_chain):
                first_sum = quicksum(
                    decision_variables.lambda_total[arc, p, p_prime] for arc in vnf_chain[1:index + 1] for p_prime in
                    paths_different_from_p)
                second_sumand = decision_variables.lambda_total[pair, p, p]
                third_sum = quicksum(
                    decision_variables.lambda_total[arc, p_prime, p] for arc in vnf_chain[index:] for p_prime in
                    paths_different_from_p)

                inner_sums = model.addVar(lb=0)
                model.addConstr(inner_sums == first_sum + second_sumand + third_sum)
                boxes.append(inner_sums)

            dec_var = model.addVar(name=request_key + "_" + p, lb=0)
            model.addConstr(dec_var == max_(boxes))
            decision_vars.append(dec_var)

        model.addConstr(quicksum(decision_vars) + quicksum(
            decision_variables.lambda_intra[arc, p_prime, p_prime_prime, p] for arc in indices.arcs for p_prime in
            paths_different_from_p
            for p_prime_prime in paths_different_from_p) == decision_variables.beta[p])


# 18. can only route to existing vnfs with intra domain paths
def __route_from_existing_vnfs_intra_constraint(parameters, indices, decision_variables, model):
    for arc, p, p_prime, p_prime_prime in itertools.product(indices.arcs, indices.paths, indices.paths,
                                                            indices.paths):
        starting_vnf = get_vnf_from_arc(arc[0])
        model.addConstr(
            decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime] <= bigM * decision_variables.gamma[
                starting_vnf, p])


# 19. only route to exisiting vnfs with intra domain paths
def __route_to_existing_vnfs_intra_constraint(parameters, indices, decision_variables, model):
    for arc, p, p_prime, p_prime_prime in itertools.product(indices.arcs, indices.paths, indices.paths,
                                                            indices.paths):
        ending_vnf = get_vnf_from_arc(arc[1])
        model.addConstr(
            decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime] <= bigM * decision_variables.gamma[
                ending_vnf, p_prime])


# 20. only route from exsiting vnfs on inter domain edges
def __route_from_existing_vnfs_inter_constraint(parameters, indices, decision_variables, model):
    for arc, p, p_prime, e in itertools.product(indices.arcs, indices.paths, indices.paths, indices.edges):
        model.addConstr(
            decision_variables.lambda_inter[arc, p, p_prime, e] <= decision_variables.lambda_total[arc, p, p_prime])


# 21. only route to exisiting vnfs with inter domain edges
def __route_to_existing_vnfs_inter_constraint(parameters, indices, decision_variables, model):
    for arc, p, p_prime, e in itertools.product(indices.arcs, indices.paths, indices.paths, indices.edges):
        model.addConstr(
            decision_variables.lambda_inter[arc, p, p_prime, e] <= decision_variables.lambda_total[arc, p, p_prime])


# 22. Flow conservation at ending paths
def __lambda_total_matches_incoming_rates_constraint(parameters, indices, decision_variables, model):
    for arc, p, p_prime in itertools.product(indices.arcs, indices.paths, indices.paths):
        intra_domain_paths = parameters.network_description[key_intra_domain_paths]
        inter_domain_edges = parameters.network_description[key_inter_domain_edges]
        border_node = intra_domain_paths[p_prime]["src"]
        paths_ending_at_border_node = [path_key for path_key, path_value in intra_domain_paths.items() if
                                       path_value["dst"] == border_node]
        edges_ending_at_border_node = [edge_key for edge_key, edge_value in inter_domain_edges.items() if
                                       edge_value["dst"] == border_node]

        paths_starting_at_border_node = [path_key for path_key, path_value in intra_domain_paths.items() if
                                         path_value["src"] == border_node]
        edges_starting_at_border_node = [edge_key for edge_key, edge_value in inter_domain_edges.items() if
                                         edge_value["src"] == border_node]

        # this traffic was routed by the placement decision
        if p != p_prime and p not in paths_ending_at_border_node:
            model.addConstr(
                quicksum(
                    decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime] for p_prime_prime in
                    paths_starting_at_border_node if p_prime != p_prime_prime) + quicksum(
                    decision_variables.lambda_inter[arc, p, p_prime, edge] for edge in
                    edges_starting_at_border_node) +
                decision_variables.lambda_total[arc, p, p_prime] == quicksum(
                    decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime] for p_prime_prime in
                    paths_ending_at_border_node if p_prime != p_prime_prime) + quicksum(
                    decision_variables.lambda_inter[arc, p, p_prime, edge] for edge in
                    edges_ending_at_border_node)
            )
        if p in paths_ending_at_border_node:
            model.addConstr(
                quicksum(
                    decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime] for p_prime_prime in
                    paths_starting_at_border_node if p_prime != p_prime_prime) + quicksum(
                    decision_variables.lambda_inter[arc, p, p_prime, edge] for edge in
                    edges_starting_at_border_node) == quicksum(
                    decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime] for p_prime_prime in
                    paths_ending_at_border_node if p_prime != p_prime_prime) + quicksum(
                    decision_variables.lambda_inter[arc, p, p_prime, edge] for edge in
                    edges_ending_at_border_node))


# 23. flow conservation at starting paths
def __lambda_total_outgoing_rates_constraint(parameters, indices, decision_variables, model):
    for arc, p, p_prime in itertools.product(indices.arcs, indices.paths, indices.paths):
        inter_domain_edges = parameters.network_description[key_inter_domain_edges]
        intra_domain_paths = parameters.network_description[key_intra_domain_paths]
        # starting VNF was placed in p hence the destination has to get rid of the traffic
        border_node = intra_domain_paths[p]["dst"]
        paths_starting_at_border_node = [path_key for path_key, path_value in intra_domain_paths.items() if
                                         path_value["src"] == border_node]
        edges_starting_at_border_node = [edge_key for edge_key, edge_value in inter_domain_edges.items() if
                                         edge_value["src"] == border_node]

        paths_ending_at_border_node = [path_key for path_key, path_value in intra_domain_paths.items() if
                                       path_value["dst"] == border_node]

        edges_ending_at_border_node = [edge_key for edge_key, edge_value in inter_domain_edges.items() if
                                       edge_value["dst"] == border_node]
        if p != p_prime and p_prime not in paths_starting_at_border_node:
            # get rid of all traffic
            model.addConstr(
                quicksum(
                    decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime] for p_prime_prime in
                    paths_ending_at_border_node if p_prime != p_prime_prime) + quicksum(
                    decision_variables.lambda_inter[arc, p, p_prime, edge] for edge in
                    edges_ending_at_border_node) + \
                decision_variables.lambda_total[arc, p, p_prime] == quicksum(
                    decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime] for p_prime_prime in
                    paths_starting_at_border_node if p_prime != p_prime_prime) + quicksum(
                    decision_variables.lambda_inter[arc, p, p_prime, edge] for edge in
                    edges_starting_at_border_node))
        if p_prime in paths_starting_at_border_node:
            model.addConstr(quicksum(
                decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime] for p_prime_prime in
                paths_starting_at_border_node if p_prime != p_prime_prime) + quicksum(
                decision_variables.lambda_inter[arc, p, p_prime, edge] for edge in
                edges_starting_at_border_node) == quicksum(
                decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime] for p_prime_prime in
                paths_ending_at_border_node if p_prime != p_prime_prime) + quicksum(
                decision_variables.lambda_inter[arc, p, p_prime, edge] for edge in
                edges_ending_at_border_node))


# 24. no SRC or DST placement
def __no_src_dst_placement_constraint(parameters, indices, decision_variables, model):
    for path in indices.paths:
        if "ingress" in path or "egress" in path:
            model.addConstr(decision_variables.gamma["SRC", path] + decision_variables.gamma["DST", path] == 1)
        else:
            model.addConstr(decision_variables.gamma["SRC", path] + decision_variables.gamma["DST", path] == 0)


# 25. restrict the network from routing over intermediate paths
def __no_flow_over_intermediate_paths_constraint(parameters, indices, decision_variables, model):
    for arc, p, p_prime, p_prime_prime in itertools.product(indices.arcs, indices.paths, indices.paths,
                                                            indices.paths):
        if "ingress" in p_prime_prime or "egress" in p_prime_prime:
            model.addConstr(decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime] == 0)


# 26. total flow has to match the initial flow
def __total_flow_matches_expected_flow_constraint(parameters, indices, decision_variables, model):
    for arc in indices.arcs:
        request_key = get_request_from_arc(arc[0])
        request = parameters.vnf_requests[request_key]
        ingress = request["ingress"]
        egress = request["egress"]
        initial_rate = request["initial_rate"]
        outgoing_rate = initial_rate

        for tup in parameters.chains[request["vnf_chain"]]:
            if tup[1] == get_vnf_from_arc(arc[1]):
                break
            outgoing_rate = evaluate_outgoing_rate(parameters=parameters, vnf=tup[1], ingoing_rate=outgoing_rate)

        if "SRC" in arc[0]:
            model.addConstr(quicksum(
                decision_variables.lambda_total[arc, "ingress_" + ingress, p_prime] for p_prime in
                indices.paths) == initial_rate)
            model.addConstr(quicksum(
                decision_variables.lambda_total[arc, p, p_prime] for p in indices.paths for p_prime in
                indices.paths if p != "ingress_" + ingress) == 0)
        elif "DST" in arc[1]:
            model.addConstr(quicksum(
                decision_variables.lambda_total[arc, p_prime, "egress_" + egress] for p_prime in
                indices.paths) == outgoing_rate)
        else:
            # pass
            # this constraint can be left out but enabling it speeds up the optimization
            model.addConstr(quicksum(
                decision_variables.lambda_total[arc, p, p_prime] for p in indices.paths for p_prime in
                indices.paths) == outgoing_rate)


# 27. paths that are not a part of a shared cpu constraint cannot use its cpu
def __shared_cpu_for_unrelated_paths_constraint(parameters, indices, decision_variables, model):
    for cpu_restriction, path in itertools.product(indices.cpu_restrictions, indices.paths):
        if path not in parameters.advertised_restrictions["cpu_restrictions"][cpu_restriction]["paths"]:
            model.addConstr(decision_variables.epsilon[cpu_restriction, path] == 0)


# 28. path capacity must not be exceeded
def __path_capacity_constraint(parameters, indices, decision_variables, model):
    for path in indices.paths:
        model.addConstr(decision_variables.beta[path] <= int(get_rate_of_path(parameters=parameters, path=path)),
                        name="max_rate_on_paths_" + path)


# 29.
def __advertised_path_capacity_constraint(parameters, indices, decision_variables, model):
    for routing_restriction in indices.routing_restrictions:
        shared_paths = parameters.advertised_restrictions["routing_restrictions"][routing_restriction]["paths"]
        shared_bottleneck = parameters.advertised_restrictions["routing_restrictions"][routing_restriction][
            "shared_bottleneck"]
        model.addConstr(quicksum(decision_variables.beta[path] for path in shared_paths) <= shared_bottleneck,
                        name="shared_bottleneck_" + str(shared_bottleneck))


# 30
def __backward_edge_constraint(parameters, indices, decision_variables, model):
    if "routing_restriction_edges" in parameters.advertised_restrictions:
        for routing_restriciton_edge_key, routing_restriction_edge in parameters.advertised_restrictions[
            "routing_restriction_edges"].items():
            shared_rate = routing_restriction_edge["shared_bottleneck"]
            edges = routing_restriction_edge["edges"]
            model.addConstr(quicksum(
                decision_variables.lambda_inter[arc, p, p_prime, e] for arc in indices.arcs for p in indices.paths for
                p_prime in indices.paths for e in edges) <= shared_rate,
                            name="shared_edge_bottleneck_" + routing_restriciton_edge_key)


# 31
def __lambda_distribution_constraint(parameters, indices, decision_variables, model):
    for vnf, path in itertools.product(indices.vnfs, indices.paths):
        if "SRC" in vnf or "DST" in vnf or "ingress" in path or "egress" in path:
            continue
        for request in parameters.vnf_requests.keys():
            arc_ending_with_vnf = next((arc for arc in indices.arcs if
                                        vnf == get_vnf_from_arc(arc[1]) and request == get_request_from_arc(arc[1])),
                                       None)
            arc_starting_with_vnf = next((arc for arc in indices.arcs if
                                          vnf == get_vnf_from_arc(arc[0]) and request == get_request_from_arc(arc[0])),
                                         None)
            if arc_ending_with_vnf is not None and arc_starting_with_vnf is not None:
                # all the outgoing traffic of a VNF has to be distributed among requests
                model.addConstr(evaluate_outgoing_rate(parameters=parameters, vnf=vnf, ingoing_rate=
                quicksum(decision_variables.lambda_total[arc_ending_with_vnf, p_prime, path] for p_prime in
                         indices.paths)) == quicksum(
                    decision_variables.lambda_total[arc_starting_with_vnf, path, p_prime] for p_prime in
                    indices.paths),
                                name="lambda_distribution_" + vnf + "_" + path)


def __delay_definition(parameters, indices, decision_variables, model):
    inter_domain_edges = parameters.network_description[key_inter_domain_edges]
    intra_domain_paths = parameters.network_description[key_intra_domain_paths]
    for arc, p, p_prime, border_node in itertools.product(indices.arcs, indices.paths, indices.paths,
                                                          indices.border_nodes):
        paths_ending_at_border_node = [path_key for path_key, path_value in intra_domain_paths.items() if
                                       path_value["dst"] == border_node]
        edges_ending_at_border_node = [edge_key for edge_key, edge_value in inter_domain_edges.items() if
                                       edge_value["dst"] == border_node]
        # check if b is the destination of p (i.e. a new placement situation)
        if parameters.network_description[key_intra_domain_paths][p]["dst"] != border_node:
            all_paths_or_edges = []

            for p_prime_prime in paths_ending_at_border_node:
                delay_of_path = parameters.network_description[key_intra_domain_paths][p_prime_prime]["delay"]
                source_of_path = parameters.network_description[key_intra_domain_paths][p_prime_prime]["src"]
                intra_path = model.addVar(lb=0, name="{3}_max_of_{0}_node_{1}_via_path_{2}".format(border_node,
                                                                                                   source_of_path,
                                                                                                   p_prime_prime, arc))

                model.addGenConstrIndicator(
                    decision_variables.delta_intra[arc, p, p_prime, p_prime_prime], True,
                    intra_path == decision_variables.zeta[
                        arc, p, p_prime, source_of_path] + delay_of_path)

                all_paths_or_edges.append(intra_path)

            for e in edges_ending_at_border_node:
                inter_edge = model.addVar(lb=0)
                delay_of_edge = parameters.network_description[key_inter_domain_edges][e]["delay"]
                source_of_edge = parameters.network_description[key_inter_domain_edges][e]["src"]

                model.addGenConstrIndicator(
                    decision_variables.delta_inter[arc, p, p_prime, e], True, inter_edge == (decision_variables.zeta[
                                                                                                 arc, p, p_prime, source_of_edge] +
                                                                                             decision_variables.delta_inter[
                                                                                                 arc, p, p_prime, e] * delay_of_edge))

                all_paths_or_edges.append(inter_edge)

            if len(all_paths_or_edges) > 0:
                model.addConstr(decision_variables.zeta[arc, p, p_prime, border_node] == max_(all_paths_or_edges))
                logger.debug("Added constraint of length {0}".format(len(all_paths_or_edges)))
        else:
            # on p was a placement -> thus figure out was the max delay before that placement was!
            preceding_arc = next((pred_arc for pred_arc in indices.arcs if pred_arc[1] == arc[0]), None)

            if preceding_arc is not None:
                delay_of_path = parameters.network_description[key_intra_domain_paths][p]["delay"]
                other_placements = []
                b_prime = parameters.network_description[key_intra_domain_paths][p]["src"]

                for p_prime_prime in indices.paths:

                    if p == p_prime_prime:
                        continue

                    placement = model.addVar(lb=0)

                    model.addConstr(
                        placement == decision_variables.zeta[preceding_arc, p_prime_prime, p, b_prime] + delay_of_path)

                    other_placements.append(placement)

                max_over_other_paths = model.addVar(lb=0)
                model.addConstr(max_over_other_paths == max_(other_placements))
                model.addGenConstrIndicator(decision_variables.gamma[get_vnf_from_arc(arc[0]), p], False,
                                            decision_variables.zeta[arc, p, p_prime, border_node] == 0)
                model.addGenConstrIndicator(decision_variables.gamma[get_vnf_from_arc(arc[0]), p], True,
                                            decision_variables.zeta[
                                                arc, p, p_prime, border_node] == max_over_other_paths)

            else:
                # we are looking at the temp path
                model.addConstr(decision_variables.zeta[arc, p, p_prime, border_node] == 0)


def __route_between_exisitng_instances_constraint(parameters, indices, decision_variables, model):
    for arc, p, p_prime in itertools.product(indices.arcs, indices.paths, indices.paths):
        model.addConstr(decision_variables.lambda_total[arc, p, p_prime] <= bigM * decision_variables.gamma[
            get_vnf_from_arc(arc[0]), p])
        model.addConstr(decision_variables.lambda_total[arc, p, p_prime] <= bigM * decision_variables.gamma[
            get_vnf_from_arc(arc[1]), p_prime])


def __define_restrictions(parameters, indices, decision_variables, model, with_delay_constraints):
    # 1.
    __outrate_constraint(parameters, indices, decision_variables, model)
    # 2.
    __cpu_consumption_constraint(parameters, indices, decision_variables, model)
    # 3.
    __inter_domain_edge_capacity_constraint(parameters, indices, decision_variables, model)
    # 4.
    __bigM_inter_domain_edge_constraint(parameters, indices, decision_variables, model)
    # 5.
    __bigM_intra_domain_path_constraint(parameters, indices, decision_variables, model)
    # 6.
    __bigM_placement_constraint(parameters, indices, decision_variables, model)
    # 7.
    __outrate_distribution_constraint(parameters, indices, decision_variables, model)
    # 8.
    __inrate_distribution_constraint(parameters, indices, decision_variables, model)
    # 9.
    __cpu_capacity_constraint(parameters, indices, decision_variables, model)
    # 10.
    __advertised_cpu_capacity_constraint(parameters, indices, decision_variables, model)
    # 11.
    if with_delay_constraints:
        __max_delay_request_constraint(parameters, indices, decision_variables, model)
    # 12.
    __ingress_placement_constraint(parameters, indices, decision_variables, model)
    # 13.
    __ingress_initial_rate_constraint(parameters, indices, decision_variables, model)
    # 14.
    __egress_placement_constraint(parameters, indices, decision_variables, model)
    # 15.
    __egress_final_rate_constraint(parameters, indices, decision_variables, model)
    # 16.
    __flow_conservation_border_nodes_constraint(parameters, indices, decision_variables, model)
    # 17.
    __max_rate_def_constraint(parameters, indices, decision_variables, model)
    # 18.
    __route_from_existing_vnfs_intra_constraint(parameters, indices, decision_variables, model)
    # 19.
    __route_to_existing_vnfs_intra_constraint(parameters, indices, decision_variables, model)
    # 20.
    __route_from_existing_vnfs_inter_constraint(parameters, indices, decision_variables, model)
    # 21.
    __route_to_existing_vnfs_inter_constraint(parameters, indices, decision_variables, model)
    # 22.
    __lambda_total_matches_incoming_rates_constraint(parameters, indices, decision_variables, model)
    # 23.
    __lambda_total_outgoing_rates_constraint(parameters, indices, decision_variables, model)
    # 24.
    __no_src_dst_placement_constraint(parameters, indices, decision_variables, model)
    # 25.
    __no_flow_over_intermediate_paths_constraint(parameters, indices, decision_variables, model)
    # 26.
    __total_flow_matches_expected_flow_constraint(parameters, indices, decision_variables, model)
    # 27.
    __shared_cpu_for_unrelated_paths_constraint(parameters, indices, decision_variables, model)
    # 28.
    __path_capacity_constraint(parameters, indices, decision_variables, model)
    # 29.
    __advertised_path_capacity_constraint(parameters, indices, decision_variables, model)
    # 30.
    __backward_edge_constraint(parameters, indices, decision_variables, model)
    # 31.
    __lambda_distribution_constraint(parameters, indices, decision_variables, model)
    # 32.
    if with_delay_constraints:
        __delay_definition(parameters, indices, decision_variables, model)
    __route_between_exisitng_instances_constraint(parameters, indices, decision_variables, model)


def get_model(network_description_file, vnf_description_file, chain_description_file,
              vnf_request_description_file, advertised_restriction_file, generate_backward_paths=True,
              with_delay_constraints=False):
    """
    Defines the gurobipy model from the given parameter files, however it does not solve model.
    :param network_description_file: a yaml file specifying the network structure
    :param vnf_description_file:  a yaml file describing the vnfs
    :param chain_description_file: a yaml file describing all used vnf chains
    :param vnf_request_description_file: a yaml file describing all vnf requests
    :param advertised_restriction_file:  a yaml file describing all advertised restrictions from the child coordinators
    :return: the parsed parameters, the used indices, the defined decision variables and the filled gurobipy model
    """
    parameters = __load_descriptions(network_description_file, vnf_description_file, chain_description_file,
                                     vnf_request_description_file, advertised_restriction_file)

    indices = __define_indices(parameters)

    if generate_backward_paths:
        __add_backward_edges(parameters)

    # add the temporary nodes for the ingresses/egresses where the SRC and DST VNFs will be placed on
    __add_temporary_nodes_and_paths(parameters, indices)

    model = Model("gurobipy_mip")
    decision_variables = __define_decision_variables(parameters=parameters, indices=indices, model=model)
    __define_restrictions(parameters, indices, decision_variables, model, with_delay_constraints)

    model.setObjectiveN(
        quicksum(decision_variables.gamma[vnf, path] for vnf, path in
                 itertools.product(indices.vnfs, indices.paths)) + quicksum(
            decision_variables.delta_inter[arc, p, p_prime, e] * get_delay_of_link(parameters, e) for arc, p, p_prime, e
            in
            itertools.product(indices.arcs, indices.paths, indices.paths,
                              indices.edges)) + quicksum(
            decision_variables.delta_intra[arc, p, p_prime, p_prime_prime] * get_delay_of_path(parameters,
                                                                                               p_prime_prime)
            for arc, p, p_prime, p_prime_prime in
            itertools.product(indices.arcs, indices.paths, indices.paths,
                              indices.paths)),
        index=0, priority=3, weight=1.0)

    model.setObjectiveN(quicksum(
        decision_variables.delta_inter[arc, p, p_prime, e] * get_delay_of_link(parameters, e) for arc, p, p_prime, e in
        itertools.product(indices.arcs, indices.paths, indices.paths,
                          indices.edges)) + quicksum(
        decision_variables.delta_intra[arc, p, p_prime, p_prime_prime] * get_delay_of_path(parameters, p_prime_prime)
        for arc, p, p_prime, p_prime_prime in
        itertools.product(indices.arcs, indices.paths, indices.paths,
                          indices.paths)), index=1,
                        priority=2, weight=1.0)

    model.setObjectiveN(quicksum(
        decision_variables.delta_inter[arc, p, p_prime, e] for arc, p, p_prime, e in
        itertools.product(indices.arcs, indices.paths, indices.paths,
                          indices.edges)) + quicksum(
        decision_variables.delta_intra[arc, p, p_prime, p_prime_prime]
        for arc, p, p_prime, p_prime_prime in
        itertools.product(indices.arcs, indices.paths, indices.paths,
                          indices.paths)), index=2,
                        priority=1, weight=1.0)

    return parameters, indices, decision_variables, model


def solve_model(network_description_file, vnf_description_file, chain_description_file,
                vnf_request_description_file, advertised_restriction_file, pretty_print=False, output_file=None,
                generate_backward_paths=True, with_delay_constraints=False, max_timeout_delay=-1,
                graph_output_path=None, seed=0, use_exact_placements=-1, num_threads=6):
    """
    Defines the gurobipy model from the given parameter files, solves it, and prints the solution (if specified).
    :param network_description_file: a yaml file specifying the network structure
    :param vnf_description_file:  a yaml file describing the vnfs
    :param chain_description_file: a yaml file describing all used vnf chains
    :param vnf_request_description_file: a yaml file describing all vnf requests
    :param advertised_restriction_file:  a yaml file describing all advertised restrictions from the child coordinators
    :param pretty_print: whether or not the solution shall be printed to stdout
    :param output_file: a path to a file where the solution shall be dumped to
    :param generate_backward_paths: True, if the provided graph only contains forward paths
    :param with_delay_constraints: True, if the delay of a request should be bounded (impacts runtime)
    :param max_timeout_delay: the maximal timeout the optimizing system should take to minimize the delay,
     -1 if unbounded
    :return: the parsed parameters, the used indices, the defined decision variables and the filled gurobipy model
    """
    parameters, indices, decision_variables, model = get_model(network_description_file, vnf_description_file,
                                                               chain_description_file,
                                                               vnf_request_description_file,
                                                               advertised_restriction_file,
                                                               generate_backward_paths=generate_backward_paths,
                                                               with_delay_constraints=with_delay_constraints)

    if graph_output_path is not None:
        plot_network(parameters, graph_output_path)

    ## set gurobi vars ##
    env1 = model.getMultiobjEnv(1)
    env1.setParam(GRB.Param.Seed, int(seed))
    env1.setParam(GRB.Param.Threads, num_threads)
    env2 = model.getMultiobjEnv(0)
    env2.setParam(GRB.Param.Seed, int(seed))
    env2.setParam(GRB.Param.Threads, num_threads)

    ## set placements ##
    if use_exact_placements != -1:
        model.addConstr(quicksum(decision_variables.gamma[j, p] for j in indices.vnfs for p in
                        indices.paths) == use_exact_placements)

    model.optimize()

    if pretty_print:
        pretty_print_solution(indices=indices, decision_variables=decision_variables, model=model)

    if output_file is not None:
        save_solution(indices=indices, decision_variables=decision_variables, model=model, output_path=output_file)

    return parameters, indices, decision_variables, model
