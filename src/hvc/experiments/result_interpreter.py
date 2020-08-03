import networkx as nx
import yaml
from networkx.algorithms.dag import dag_longest_path

from hvc.api.graphml import __read_graph, read_hierarchy


def interpret_results(graphml_path, vnf_requests_path, hierarchy_path, solution_path, chains_path):
    """
    Calculates the amount of VNF placements, total-delay per request, maximal end-to-end delay per request
     and the evaluation time of a solution
    :param graphml_path: the path to the graphml file of the network (needed for computing end-to-end delay)
    :param solution_path: the path where the solution files reside in
    :return:
    """
    G = __read_graph(graphml_path)
    with open(vnf_requests_path, 'r') as vnf_requests_file, \
            open(solution_path + "/overlay_solution.yaml", 'r') as overlay_solution_file, \
            open(solution_path + "/time_delta.yaml", 'r') as time_delta_file, \
            open(chains_path, 'r') as chains_file:
        overlay_solution = yaml.load(overlay_solution_file, Loader=yaml.FullLoader)
        vnf_requests = yaml.load(vnf_requests_file, Loader=yaml.FullLoader)
        time_deltas = yaml.load(time_delta_file, Loader=yaml.FullLoader)
        vnf_chains = yaml.load(chains_file, Loader=yaml.FullLoader)

        root_coordinator = read_hierarchy(hierarchy_path)
        total_delay_map = {}
        end2end_delay_map = {}
        for request in vnf_requests.keys():
            end2end_delay_map[request] = calculate_end_to_end_delay(G, overlay_solution, vnf_requests, request,
                                                                    vnf_chains)
            edges = __get_edges_from_solution(request, overlay_solution)
            total_delay_map[request] = calculate_total_delay(G, edges)

        solving_time = calculate_time_recursively(root_coordinator, time_deltas)
        placements = len([k for k in overlay_solution.keys() if "gamma" in k])
        return placements, total_delay_map, end2end_delay_map, solving_time


def calculate_time_recursively(coordinator, time_deltas):
    if coordinator.name not in time_deltas:
        return 0
    own_time = time_deltas[coordinator.name]
    if len(coordinator.child_coordinators) == 0:
        return own_time
    else:
        child_times = [calculate_time_recursively(child, time_deltas) for child in coordinator.child_coordinators]
        return own_time + max(child_times)


def calculate_end_to_end_delay(G, overlay_solution, vnf_requests, request, vnf_chains):
    """
    Takes the solution edges and reconstructs a di-graph. Then, calculates the longest path using the networkx lib.
     """
    chain_key = vnf_requests[request]['vnf_chain']
    arcs = vnf_chains[chain_key]

    total_e2e_delay = 0
    for arc in arcs:
        edges = __get_edges_from_solution_for_arc(request, overlay_solution, arc)
        total_e2e_delay += calculate_end_to_end_delay_for_arc(G, edges)
    return total_e2e_delay


def calculate_end_to_end_delay_for_arc(G, edges):
    adjusted_edges = [__get_edge_id_from_label(e) for e in edges]
    dG = nx.DiGraph()
    added_nodes = []
    for u, v in G.edges():
        if G[u][v]['id'] in adjusted_edges:
            if u not in added_nodes:
                dG.add_node(u, **G.nodes[u])
                added_nodes.append(u)
            if v not in added_nodes:
                dG.add_node(v, **G.nodes[v])
                added_nodes.append(v)
            dG.add_edge(u, v, **G[u][v])

    longest_path = dag_longest_path(dG, weight="delay")

    if len(longest_path) == 0:
        return 0
    path_iter = iter(longest_path)
    u = next(path_iter)
    delay = 0
    for v in path_iter:
        delay += dG[u][v]['delay']
        u = v
    return delay


def calculate_total_delay(G, edges):
    adjusted_edges = [__get_edge_id_from_label(e) for e in edges]
    return sum(G[u][v]['delay'] for (u, v) in G.edges() if G[u][v]['id'] in adjusted_edges)


def __get_edge_id_from_label(label):
    if "edge" in label:
        return int(label[label.index("edge_") + 5:])
    else:
        return int(label)


def __get_edges_from_solution_for_arc(request, solution_file, arc):
    edges = []
    for k in solution_file.keys():
        if 'inter' in k and request in k and arc[0] in k and arc[1] in k:
            edge = k[k.rindex(',') + 2:k.index(']')]
            edges.append(edge)
    return edges


def __get_edges_from_solution(request, solution_file):
    edges = []
    for k in solution_file.keys():
        if 'inter' in k and request in k:
            edge = k[k.rindex(',') + 2:k.index(']')]
            edges.append(edge)
    return edges
