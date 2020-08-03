# noinspection PyUnresolvedReferences
import logging
from collections import defaultdict
import xml.etree.ElementTree as ET
import networkx as nx
import yaml
from gurobipy import *
from networkx.drawing.nx_pydot import write_dot

formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')


def setup_logger(name, log_file, level=logging.DEBUG):
    """To setup as many loggers as you want"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = logging.FileHandler(log_file)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


key_intra_domain_paths = "intra_domain_paths"
key_inter_domain_edges = "inter_domain_edges"
key_outgoing_rate = "outgoing_rate"
key_cpu_restrictions = "cpu_restrictions"
key_routing_restrictions = "routing_restrictions"


def log_solution(indices, decision_variables, model, logger):
    tol = 1e-4
    logger.debug("# ==========================================================")
    for arc, p, p_prime in itertools.product(indices.arcs, indices.paths, indices.paths):
        if abs(decision_variables.lambda_total[arc, p, p_prime].X) > tol:
            logger.debug(decision_variables.lambda_total[arc, p, p_prime].VarName,
                         decision_variables.lambda_total[arc, p, p_prime].X)
    logger.debug("# ==========================================================")
    for arc, p, p_prime, e in itertools.product(indices.arcs, indices.paths, indices.paths, indices.edges):
        if abs(decision_variables.lambda_inter[arc, p, p_prime, e].X) > tol:
            logger.debug(decision_variables.lambda_inter[arc, p, p_prime, e].VarName,
                         decision_variables.lambda_inter[
                             arc, p, p_prime, e].X)
    logger.debug("# ==========================================================")
    logger.debug("Lambda intra")
    for arc, p, p_prime, p_prime_prime in itertools.product(indices.arcs, indices.paths, indices.paths, indices.paths):
        if abs(decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime].X) > tol:
            logger.debug(decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime].VarName,
                         decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime].X)
    logger.debug("# ==========================================================")
    for vnf, path in itertools.product(indices.vnfs, indices.paths):
        if abs(decision_variables.sigma_in[vnf, path].X) > tol:
            logger.debug(decision_variables.sigma_in[vnf, path].VarName, decision_variables.sigma_in[vnf, path].X)
    logger.debug("# ==========================================================")
    for vnf, path in itertools.product(indices.vnfs, indices.paths):
        if abs(decision_variables.sigma_out[vnf, path].X) > tol:
            logger.debug(decision_variables.sigma_out[vnf, path].VarName, decision_variables.sigma_out[vnf, path].X)
    logger.debug("# ==========================================================")
    for vnf, path in itertools.product(indices.vnfs, indices.paths):
        if abs(decision_variables.gamma[vnf, path].X) > tol:
            logger.debug(decision_variables.gamma[vnf, path].VarName, decision_variables.gamma[vnf, path].X)
    logger.debug("# ==========================================================")
    for vnf, path in itertools.product(indices.vnfs, indices.paths):
        if abs(decision_variables.kappa[vnf, path].X) > tol:
            logger.debug(decision_variables.kappa[vnf, path].VarName, decision_variables.kappa[vnf, path].X)
    logger.debug("# ==========================================================")
    for cpu_restriction, path in itertools.product(indices.cpu_restrictions, indices.paths):
        if abs(decision_variables.epsilon[cpu_restriction, path].X) > tol:
            logger.debug(decision_variables.epsilon[cpu_restriction, path].VarName,
                         decision_variables.epsilon[cpu_restriction, path].X)
    logger.debug("# ==========================================================")
    for path in indices.paths:
        if abs(decision_variables.beta[path].X) > tol:
            logger.debug(decision_variables.beta[path].VarName, decision_variables.beta[path].X)


def save_solution(indices, decision_variables, model, output_path):
    condensed_solution_dict = output_path + "/solution.log"
    full_solution_dict = output_path +"/full_solution.log"
    with open(condensed_solution_dict, 'w') as condensed_file, open(full_solution_dict, 'w') as full_solution_file:
        solution_dict = {}
        condensed_solution_dict = defaultdict(int)
        tol = 1e-4
        for arc, p, p_prime in itertools.product(indices.arcs, indices.paths, indices.paths):
            if abs(decision_variables.lambda_total[arc, p, p_prime].X) > tol:
                solution_dict[decision_variables.lambda_total[arc, p, p_prime].VarName] = \
                    decision_variables.lambda_total[arc, p, p_prime].X

        for arc, p, p_prime, e in itertools.product(indices.arcs, indices.paths, indices.paths, indices.edges):
            if abs(decision_variables.lambda_inter[arc, p, p_prime, e].X) > tol:
                key = "lambda_inter[({0},{1}), {2}, {3}, {4}]".format(get_original_request_from_arc(arc[0]),
                                                                      get_original_request_from_arc(arc[1]), p, p_prime,
                                                                      e)
                solution_dict[decision_variables.lambda_inter[arc, p, p_prime, e].VarName] = \
                    decision_variables.lambda_inter[arc, p, p_prime, e].X
                solution_dict[decision_variables.delta_inter[arc, p, p_prime, e].VarName] = \
                    decision_variables.delta_inter[arc, p, p_prime, e].X
                condensed_solution_dict[key] += decision_variables.lambda_inter[arc, p, p_prime, e].X

        for arc, p, p_prime, p_prime_prime in itertools.product(indices.arcs, indices.paths, indices.paths,
                                                                indices.paths):
            if abs(decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime].X) > tol:
                solution_dict[decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime].VarName] = \
                    decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime].X
                solution_dict[decision_variables.delta_intra[arc, p, p_prime, p_prime_prime].VarName] = \
                    decision_variables.delta_intra[arc, p, p_prime, p_prime_prime].X

        for vnf, path in itertools.product(indices.vnfs, indices.paths):
            if abs(decision_variables.sigma_in[vnf, path].X) > tol:
                solution_dict[decision_variables.sigma_in[vnf, path].VarName] = \
                    decision_variables.sigma_in[vnf, path].X

        for vnf, path in itertools.product(indices.vnfs, indices.paths):
            if abs(decision_variables.sigma_out[vnf, path].X) > tol:
                solution_dict[decision_variables.sigma_out[vnf, path].VarName] = \
                    decision_variables.sigma_out[vnf, path].X

        for vnf, path in itertools.product(indices.vnfs, indices.paths):
            if abs(decision_variables.gamma[vnf, path].X) > tol:
                key = "gamma[{0}, {1}]".format(vnf, path)
                solution_dict[decision_variables.gamma[vnf, path].VarName] = \
                    decision_variables.gamma[vnf, path].X
                condensed_solution_dict[key] = decision_variables.gamma[vnf, path].X

        for vnf, path in itertools.product(indices.vnfs, indices.paths):
            if abs(decision_variables.kappa[vnf, path].X) > tol:
                solution_dict[decision_variables.kappa[vnf, path].VarName] = \
                    decision_variables.kappa[vnf, path].X

        for cpu_restriction, path in itertools.product(indices.cpu_restrictions, indices.paths):
            if abs(decision_variables.epsilon[cpu_restriction, path].X) > tol:
                solution_dict[decision_variables.epsilon[cpu_restriction, path].VarName] = \
                    decision_variables.epsilon[cpu_restriction, path].X

        for path in indices.paths:
            if abs(decision_variables.beta[path].X) > tol:
                solution_dict[decision_variables.beta[path].VarName] = \
                    decision_variables.beta[path].X
        yaml.dump(dict(condensed_solution_dict), condensed_file)
        yaml.dump(solution_dict, full_solution_file)


def pretty_print_solution(indices, decision_variables, model, natural_language=False):
    tol = 1e-4
    print("# ==========================================================")
    for arc, p, p_prime in itertools.product(indices.arcs, indices.paths, indices.paths):
        if abs(decision_variables.lambda_total[arc, p, p_prime].X) > tol:
            if natural_language:
                print(
                    "Total traffic from VNF '{0}' placed on path '{1}' to VNF '{2}' placed on path '{3}' is: {4}".format(
                        arc[0], p,
                        arc[1],
                        p_prime,
                        decision_variables.lambda_total[
                            arc, p, p_prime].X))
            else:
                print(decision_variables.lambda_total[arc, p, p_prime].VarName,
                      decision_variables.lambda_total[arc, p, p_prime].X)
    print("# ==========================================================")
    for arc, p, p_prime, e in itertools.product(indices.arcs, indices.paths, indices.paths, indices.edges):
        if abs(decision_variables.lambda_inter[arc, p, p_prime, e].X) > tol:
            if natural_language:
                print("Routed traffic from VNF '{0}' placed on '{1}' to VNF '{2}' placed on '{3}'"
                      " over the inter-domain edge '{4}' is: {5}".format(arc[0], p, arc[1], p_prime, e,
                                                                         decision_variables.lambda_inter[
                                                                             arc, p, p_prime, e].X))
            else:
                print(decision_variables.lambda_inter[arc, p, p_prime, e].VarName,
                      decision_variables.lambda_inter[
                          arc, p, p_prime, e].X)
    print("# ==========================================================")
    for arc, p, p_prime, p_prime_prime in itertools.product(indices.arcs, indices.paths, indices.paths,
                                                            indices.paths):
        if abs(decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime].X) > tol:
            print(decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime].VarName,
                  decision_variables.lambda_intra[arc, p, p_prime, p_prime_prime].X)
    print("# ==========================================================")
    for vnf, path in itertools.product(indices.vnfs, indices.paths):
        if abs(decision_variables.sigma_in[vnf, path].X) > tol:
            print(decision_variables.sigma_in[vnf, path].VarName, decision_variables.sigma_in[vnf, path].X)
    print("# ==========================================================")
    for vnf, path in itertools.product(indices.vnfs, indices.paths):
        if abs(decision_variables.sigma_out[vnf, path].X) > tol:
            print(decision_variables.sigma_out[vnf, path].VarName, decision_variables.sigma_out[vnf, path].X)
    print("# ==========================================================")
    for vnf, path in itertools.product(indices.vnfs, indices.paths):
        if abs(decision_variables.gamma[vnf, path].X) > tol:
            print(decision_variables.gamma[vnf, path].VarName, decision_variables.gamma[vnf, path].X)
    print("# ==========================================================")
    for vnf, path in itertools.product(indices.vnfs, indices.paths):
        if abs(decision_variables.kappa[vnf, path].X) > tol:
            print(decision_variables.kappa[vnf, path].VarName, decision_variables.kappa[vnf, path].X)
    print("# ==========================================================")
    for cpu_restriction, path in itertools.product(indices.cpu_restrictions, indices.paths):
        if abs(decision_variables.epsilon[cpu_restriction, path].X) > tol:
            print(decision_variables.epsilon[cpu_restriction, path].VarName,
                  decision_variables.epsilon[cpu_restriction, path].X)
    print("# ==========================================================")
    for path in indices.paths:
        if abs(decision_variables.beta[path].X) > tol:
            print(decision_variables.beta[path].VarName, decision_variables.beta[path].X)
    print("# ==========================================================")
    for arc, p, p_prime, e in itertools.product(indices.arcs, indices.paths, indices.paths, indices.edges):
        if abs(decision_variables.delta_inter[arc, p, p_prime, e].X) > tol:
            print(decision_variables.delta_inter[arc, p, p_prime, e].VarName,
                  decision_variables.delta_inter[arc, p, p_prime, e].X)
    print("# ==========================================================")
    for arc, p, p_prime, p_prime_prime in itertools.product(indices.arcs, indices.paths, indices.paths,
                                                            indices.paths):
        if abs(decision_variables.delta_intra[arc, p, p_prime, p_prime_prime].X) > tol:
            print(decision_variables.delta_intra[arc, p, p_prime, p_prime_prime].VarName,
                  decision_variables.delta_intra[arc, p, p_prime, p_prime_prime].X)
    print("# ==========================================================")
    for arc, p, p_prime, b in itertools.product(indices.arcs, indices.paths, indices.paths, indices.border_nodes):
        if abs(decision_variables.zeta[arc, p, p_prime, b].X) > tol:
            print(decision_variables.zeta[arc, p, p_prime, b].VarName,
                  decision_variables.zeta[arc, p, p_prime, b].X)


def get_backward_edge_id(forward_edge_id):
    """
    Simple helper function that makes use of the fact that the backward path of path_0 is path_1 (or the backward path
    of path_1 is path_0)
    :param forward_edge_id: the id of the forward path
    :return: the id of the backward path
    """
    path_number = int(forward_edge_id[5:])
    if path_number % 2 == 0:
        if "edge" in forward_edge_id:
            backward_edge_id = "edge_{}".format(path_number + 1)
        else:
            backward_edge_id = "path_{}".format(path_number + 1)
    else:
        if "edge" in forward_edge_id:
            backward_edge_id = "edge_{}".format(path_number - 1)
        else:
            backward_edge_id = "path_{}".format(path_number - 1)
    return backward_edge_id


def evaluate_outgoing_rate(parameters, vnf, ingoing_rate):
    """
    Helper function to evaluate the outgoing rate lambda that is marshalled as a string
    :param vnf: unique identifier of a VNF (not the component name)
    :param ingoing_rate: the ingoing_rate which defines the outgoing_rate
    :return: the evaluated lambda
    """
    lambda_string = parameters.vnf_description["outgoing_rate"][vnf]
    return eval(lambda_string)(ingoing_rate)


def evaluate_cpu_consumption(parameters, vnf, ingoing_rate):
    """
    Helper function to evaluate the cpu consumption lambda that is marshalled as a string
    :param vnf: unique identifier of a VNF (not the component name)
    :param ingoing_rate: the ingoing_rate which defines the cpu_consumption
    :return: the evaluated lambda
    """
    lambda_string = parameters.vnf_description["cpu_consumption"][vnf]
    return eval(lambda_string)(ingoing_rate)


def get_delay_of_path(parameters, path):
    return parameters.network_description[key_intra_domain_paths][path]["delay"]


def get_cpu_of_path(parameters, path):
    return parameters.network_description[key_intra_domain_paths][path]["cpu"]


def get_rate_of_path(parameters, path):
    return parameters.network_description[key_intra_domain_paths][path]["max_rate"]


def get_delay_of_link(parameters, link):
    return parameters.network_description[key_inter_domain_edges][link]["delay"]


def get_rate_of_link(parameters, link):
    return parameters.network_description[key_inter_domain_edges][link]["max_rate"]


def get_vnf_from_arc(arc):
    return arc[:arc.index("_")]


def get_request_from_arc(arc):
    return arc[arc.index("_") + 1:]


def level1_expansion(network_description_path, cpu_capacities, with_backward_paths=False, overwrite=False):
    """
    Completes the network definition with intermediate nodes and paths based on the substrate network information.
    :param parameters: the parameters including the network definition
    :param cpu_capacities: a dict mapping nodes to their cpu capacity
    :return:
    """

    with open(network_description_path, 'r') as network_description_file:
        network_description = yaml.load(network_description_file, Loader=yaml.FullLoader)

        if network_description[key_intra_domain_paths] is None:
            network_description[key_intra_domain_paths] = {}

    # first add temporary nodes for each node
    for node_list in network_description["domain_nodes"].values():
        # there is only one node in the list.
        node = node_list[0]
        node_list.append(node + "-temp")
        # now add a temporary path
        path = {
            "src": node, "dst": node + "-temp", "cpu": cpu_capacities[node], "domain": node, "delay": 0,
            "max_rate": 1000000
        }
        network_description[key_intra_domain_paths]["path" + node + "-temp"] = path

        if with_backward_paths:
            backward_path = {
                "src": node + "-temp", "dst": node, "cpu": 0, "domain": node, "delay": 0,
                "max_rate": 1000000
            }
            network_description[key_intra_domain_paths]["path" + node + "-temp-bw"] = backward_path

    if not overwrite:
        extended_network_description_path = network_description_path + "_extended"
    else:
        extended_network_description_path = network_description_path

    with open(extended_network_description_path, 'w') as network_description_file:
        yaml.dump(network_description, network_description_file)

    return extended_network_description_path


def decision_variable_is_not_zero(variable):
    tol = 1e-5
    if variable is None:
        return False
    if isinstance(variable, Var):
        return False
    return abs(variable) >= tol


def plot_network(parameters, output_path):
    network_description = parameters.network_description
    vnf_requests = parameters.vnf_requests

    G = nx.MultiDiGraph()
    node_list = []

    for domain_name, nodes in network_description["domain_nodes"].items():
        for node in nodes:
            G.add_node(node)
            node_list.append(node)

        for request_id, request in vnf_requests.items():

            if request['ingress_domain'] == domain_name and request['ingress'] not in node_list:
                G.add_node(request['ingress'])
                node_list.append(request['ingress'])

            if request['egress_domain'] == domain_name and request['egress'] not in node_list:
                G.add_node(request['egress'])
                node_list.append(request['egress'])

        for path_id, path in network_description[key_intra_domain_paths].items():
            if path['domain'] == domain_name:
                G.add_edge(path['src'], path['dst'], label=path_id)

    for edge_id, edge in network_description[key_inter_domain_edges].items():
        G.add_edge(edge['src'], edge['dst'], label=edge_id)

    write_dot(G, "{0}/graph.dot".format(output_path))


def get_original_request_from_arc(arc):
    if '-' in arc:
        #return arc[:arc.index('-')]
        return arc
    else:
        return arc

def trim_request(request):
    if '-' in request:
        return request[:request.rindex('-')]
    return request

def xml_to_gml(xml_in_path, gml_out_path):
    G = nx.Graph()
    tree = ET.parse(xml_in_path)
    root = tree.getroot()
    for child in root:
        for s_child in child:
            print(s_child.tag)
            if 'nodes' in s_child.tag:
                for node in s_child:
                    node_id = node.attrib['id']
                    coords = next(iter(node))
                    for coord in coords:
                        # logitude
                        if 'x' in coord.tag:
                            x = coord.text
                        #latitude
                        if 'y' in coord.tag:
                            y = coord.text
                    G.add_node(node_id, Longitude=x, Latitude=y)
            if 'links' in s_child.tag:
                print(s_child)
                for link in s_child:
                    for src_dst in link:
                        if 'source' in src_dst.tag:
                            u = src_dst.text
                        if 'target' in src_dst.tag:
                            v = src_dst.text
                    G.add_edge(u, v)
    nx.write_gml(G, gml_out_path)
