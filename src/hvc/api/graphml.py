import os
from datetime import datetime
from shutil import copyfile

import networkx as nx
import yaml as yaml
from networkx.drawing.nx_pydot import write_dot

import hvc.mip.gurobipy_mip as gmip
import hvc.mip.solution_interpreter as interpreter
import hvc.mip.utils as utils
from hvc.coordinator.coordinator import Coordinator

logger = utils.setup_logger("gml", "path_computing.log")

starting_timestamps = {}
ending_timestamps = {}
# in ms
delta = {}


def read_nodes(name, hierarchy):
    return hierarchy[name]['nodes']


def read_child_coordinators(name, hierarchy, level=2):
    coordinator_def = hierarchy[name]
    child_coordinators = []
    for child_coordinator, child_coordinator_def in coordinator_def['childCoordinators'].items():
        if has_children(name=child_coordinator, hierarchy=coordinator_def['childCoordinators']):
            sub_childs = read_child_coordinators(name=child_coordinator,
                                                 hierarchy=coordinator_def['childCoordinators'], level=level + 1)
            child_coordinators.append(
                Coordinator(name=child_coordinator, child_coordinators=sub_childs))
        else:
            nodes = read_nodes(name=child_coordinator, hierarchy=coordinator_def['childCoordinators'])
            child_coordinators.append(
                Coordinator(name=child_coordinator, child_coordinators=[], nodes=nodes))
    return child_coordinators


def has_children(name, hierarchy):
    return "childCoordinators" in hierarchy[name].keys()


def read_hierarchy(hierarchy_path):
    """
    Converts the hierarchy description into the objects
    :param hierarchy_path: the yaml file of the hierarchy
    :return:
    """
    with open(hierarchy_path, 'r') as hierarchy_file:
        hierarchy = yaml.load(hierarchy_file)
        root_coordinator_name = next(iter(hierarchy))
        if has_children(root_coordinator_name, hierarchy):
            child_coordinators = read_child_coordinators(root_coordinator_name, hierarchy)
            return Coordinator(name=root_coordinator_name, child_coordinators=child_coordinators,
                               is_root_coordinator=True)
        else:
            nodes = read_nodes(root_coordinator_name, hierarchy)
            return Coordinator(name=root_coordinator_name, child_coordinators=[], nodes=nodes,
                               is_root_coordinator=True)


def requests_for_coordinator_exists(path_prefix):
    return os.path.isfile("{0}/vnf_requests.yaml".format(path_prefix))


def recursively_solve_model(path_prefix, coordinator, max_timeout_delay=-1, seed=0, use_exact_placements=-1,
                            path_aggregation="full_expansion"):

    ## files were copied here
    vnf_description_file = "{0}/vnf_descriptions.yaml".format(path_prefix)
    chain_description_file = "{0}/chains.yaml".format(path_prefix)
    vnf_request_description_file = "{0}/vnf_requests.yaml".format(path_prefix)
    network_description_file = "{0}/network_description.yaml".format(path_prefix)
    advertised_restriction_file = "{0}/advertised_restrictions.yaml".format(path_prefix)

    # now set the ingress_domain field for the requests
    with open(vnf_request_description_file, 'r') as requests:
        vnf_requests = yaml.load(requests, Loader=yaml.FullLoader)
        for request_k, request_v in vnf_requests.items():
            ingress_node = request_v["ingress"]
            egress_node = request_v["egress"]

            if coordinator.is_lowest_hierarchy:
                vnf_requests[request_k]["ingress_domain"] = ingress_node
                vnf_requests[request_k]["egress_domain"] = egress_node
            else:
                for child in coordinator.child_coordinators:
                    if ingress_node in child.get_substrate_nodes():
                        vnf_requests[request_k]["ingress_domain"] = str(child.name)
                    if egress_node in child.get_substrate_nodes():
                        vnf_requests[request_k]["egress_domain"] = str(child.name)

    # save the updated requests
    with open(vnf_request_description_file, 'w') as requests:
        yaml.dump(vnf_requests, requests)

    starting_timestamps[coordinator.name] = datetime.now()
    parameters, indices, decision_vars, model = gmip.solve_model(network_description_file=network_description_file,
                                                                 chain_description_file=chain_description_file,
                                                                 vnf_description_file=vnf_description_file,
                                                                 vnf_request_description_file=vnf_request_description_file,
                                                                 advertised_restriction_file=advertised_restriction_file,
                                                                 pretty_print=True,
                                                                 output_file=path_prefix,
                                                                 with_delay_constraints=False,
                                                                 generate_backward_paths=False,
                                                                 max_timeout_delay=max_timeout_delay,
                                                                 graph_output_path=path_prefix,
                                                                 seed=seed,
                                                                 use_exact_placements=use_exact_placements)
    # solution logging...
    ending_timestamps[coordinator.name] = datetime.now()
    delta[coordinator.name] = (ending_timestamps[coordinator.name] - starting_timestamps[
        coordinator.name]).total_seconds() * 1000

    if not coordinator.is_lowest_hierarchy:
        interpreter.generate_requests_for_child_coordinators(parameters=parameters, indices=indices,
                                                             decision_variables=decision_vars, model=model,
                                                             path_prefix="{0}/".format(path_prefix))
    # if there was a new request for a child -> recursively solve it
    for child_coordinator in coordinator.child_coordinators:
        if requests_for_coordinator_exists(path_prefix="{0}/{1}".format(path_prefix, child_coordinator.name)):
            print("*********** Now solving model for coordinator {} ***********".format(child_coordinator.name))
            recursively_solve_model(path_prefix="{0}/{1}".format(path_prefix, child_coordinator.name),
                                    coordinator=child_coordinator,
                                    max_timeout_delay=max_timeout_delay, use_exact_placements=use_exact_placements)


def __read_graph(graphml_path):
    graph = nx.DiGraph(nx.read_gml(graphml_path))

    # name clash: max_rate is not a valid edge attr for gml
    for edge in graph.edges:
        edge_attr = graph.get_edge_data(*edge)
        edge_attr['max_rate'] = edge_attr['maxRate']
        edge_attr['label'] = edge_attr['id']
    return graph


def solve_graphml_model(graphml_path, vnf_description_path, chain_description_path,
                        vnf_request_description_path,
                        output_path, hierarchy_path, max_timeout_delay=-1, solution_path=None, seed=0,
                        use_exact_placements=-1, path_aggregation="full_expansion"):
    """
    Solves the vnf chaining and placement problem recursively for the given graph-ml graph.
    :param graphml_path: the graphml graph, it needs to be a directed graph, the edges need to be
     annotated with 'max_rate' and 'delay' the nodes need to be annotated with 'cpu'
    :param vnf_description_path: a yaml description of all vnfs used
    :param chain_description_path: a yaml description of all chains used
    :param vnf_request_description_path: a yaml description of all vnf requests used
    :param output_path: an absolute or relative path for the output files, folders will be created if not existant
     (i.e. network descriptions, subproblems, ...)
    :param hierarchy_path: a yaml description of a hierarchy instantiation
    :param max_timeout_delay: maximal timeout for the solving (deprecated and currently not supported)
    :param solution_path: an absolute or relative path for the solution files (i.e. overlay graph, solving times,...)
    :param seed: the gurobi seed to use
    :param use_exact_placements: can be used the set the number of placed components (only useful for flat hierarchies)
    :param path_aggregation: describes how many paths between each border nodes are advertised "full_expansion", "one_path" or "two_paths"
    :return:
    """
    valid_aggregations = ["full_expansion", "one_path", "two_paths"]
    if path_aggregation not in valid_aggregations:
        raise AssertionError(
            "Unexpected path aggregation {}, known values are {}".format(path_aggregation, valid_aggregations))
    if not os.path.exists(output_path):
        os.mkdir(output_path)

    graph = __read_graph(graphml_path)
    # write a dot file for the graph
    write_dot(graph, output_path + "/fullgraph.dot")

    root_coordinator = read_hierarchy(hierarchy_path)

    ingresses = set()
    egresses = set()

    # collect ingresses and egresses
    with open(vnf_request_description_path) as vnf_request_file:
        vnf_requests = yaml.load(vnf_request_file)
        for request_desc in vnf_requests.values():
            ingresses.add(request_desc["ingress"])
            egresses.add(request_desc["egress"])

    # build a hierarchy & compute the paths
    root_coordinator.build_hierarchy(network=graph, vnf_ingresses=list(ingresses), vnf_egresses=list(egresses))
    root_coordinator.compute_advertised_paths(path_aggregation=path_aggregation)
    root_coordinator.write_network_description(output_path)
    root_coordinator.write_advertised_restriction(output_path)

    # copy the vnf description etc to the output directory to have it all in one place
    vnf_description_file = "{0}/vnf_descriptions.yaml".format(output_path)
    chain_description_file = "{0}/chains.yaml".format(output_path)
    vnf_request_description_file = "{0}/vnf_requests.yaml".format(output_path)

    copyfile(vnf_description_path, vnf_description_file)
    copyfile(chain_description_path, chain_description_file)
    copyfile(vnf_request_description_path, vnf_request_description_file)

    # solve the model
    recursively_solve_model(output_path, root_coordinator, max_timeout_delay=max_timeout_delay, seed=seed,
                            use_exact_placements=use_exact_placements)

    # post process the results
    if solution_path is not None:
        # create solution folder
        if not os.path.exists(solution_path):
            os.mkdir(path=solution_path)
        # recursively collected solutions
        overlay_solution = dict(root_coordinator.collect_solutions(output_path))
        # save the collected solutions
        with open(solution_path + "/overlay_solution.yaml", 'w') as ofile, open(solution_path + "/starting_times.yaml",
                                                                                'w') as starting_file, open(
            solution_path + "/ending_times.yaml", 'w') as ending_file, open(solution_path + "/time_delta.yaml",
                                                                            'w') as delta_file:
            yaml.dump(overlay_solution, ofile)
            yaml.dump(delta, delta_file)
            yaml.dump(starting_timestamps, starting_file)
            yaml.dump(ending_timestamps, ending_file)
