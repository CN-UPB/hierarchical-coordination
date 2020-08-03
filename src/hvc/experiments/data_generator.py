import random as rnd

import networkx as nx
import numpy as np
import yaml
from geopy.distance import vincenty
from sklearn.cluster import KMeans

from hvc.api.graphml import __read_graph

max_rate_lb = 20
max_rate_ub = 40

cpu_lb = 8
cpu_ub = 64


def build_hierarchy(graph_input, hierarchy_output, clusters_per_hierarchy, seed=0):
    """
    Builds a hierarchy from an architecture using K-Means based clustering.
    :param graph_input:
    :param hierarchy_output:
    :param clusters_per_hierarchy:
    :param seed:
    :return:
    """
    G = __read_graph(graph_input)
    centroids = []
    index_to_centroid = {}
    counter = 0

    for index, node in enumerate(G.nodes()):
        index_to_centroid[index] = node
        if 'Latitude' in G.nodes[node]:
            x = G.nodes[node]['Longitude']
            y = G.nodes[node]['Latitude']
        elif 'graphics' in G.nodes[node]:
            x = G.nodes[node]['graphics']['x']
            y = G.nodes[node]['graphics']['y']
        elif 'x' in G.nodes[node]:
            x = G.nodes[node]['x']
            y = G.nodes[node]['y']
        else:
            raise ValueError()
        centroids.append([x, y])

    is_lowest_hierarchy = True

    for k in clusters_per_hierarchy:
        new_centroids, cluster_assignments = __k_means(centroids, k, seed)
        new_index_to_centroid = {}
        for index, centroid in enumerate(new_centroids):
            cluster = {}
            for inner_index, assigned_coord in enumerate(cluster_assignments):
                # child was assigned to this cluster
                if assigned_coord == index:
                    if is_lowest_hierarchy:
                        if 'nodes' not in cluster:
                            cluster['nodes'] = []
                        cluster['nodes'].append(index_to_centroid[inner_index])
                    else:
                        if 'childCoordinators' not in cluster:
                            cluster['childCoordinators'] = {}
                        cluster['childCoordinators'].update(index_to_centroid[inner_index])
            coordinator_name = 'coordinator{}'.format(counter)
            counter += 1
            if 'childCoordinators' in cluster and len(cluster['childCoordinators']) == 1:
                named_cluster = cluster['childCoordinators']
            else:
                named_cluster = {coordinator_name: cluster}
            new_index_to_centroid[index] = named_cluster

        index_to_centroid = new_index_to_centroid
        centroids = new_centroids
        is_lowest_hierarchy = False

    if len(index_to_centroid.values()) == 1:
        hierarchy = next(iter(index_to_centroid.values()))
    else:
        rootChilds = {}
        for child in index_to_centroid.values():
            rootChilds.update(child)
        hierarchy = {'rootCoordinator': {
            'childCoordinators': rootChilds}}
    with open(hierarchy_output, 'w') as hf:
        yaml.dump(hierarchy, hf)


def __k_means(centroids, k, seed):
    X = np.array(centroids)
    kmeans = KMeans(n_clusters=k, random_state=seed).fit(X)
    return list(kmeans.cluster_centers_), list(kmeans.labels_)


def build_graph(raw_graph_input, graph_output):
    graph = nx.Graph(nx.read_gml(raw_graph_input))
    output_graph = nx.DiGraph()

    for node in graph.nodes():
        output_graph.add_node(node, **graph.nodes[node])

    for (u, v) in graph.edges:
        attr = graph.get_edge_data(u, v)
        output_graph.add_edge(u, v, **attr)
        output_graph.add_edge(v, u, **attr)

    __fix_edge_properties(output_graph)
    __fix_node_cpu(output_graph)

    nx.write_gml(output_graph, graph_output)


def __fix_edge_properties(G):
    fixed_edges = []
    counter = 0
    for (u, v) in G.edges():
        if (v, u) not in fixed_edges:
            delay = __compute_delay_for_link(G, u, v)
            max_rate = __get_random_rate(seed=counter)
            G[u][v]['id'] = counter
            G[u][v]['delay'] = delay
            G[u][v]['maxRate'] = max_rate
            counter += 1
            G[v][u]['id'] = counter
            G[v][u]['delay'] = delay
            G[v][u]['maxRate'] = max_rate
            counter += 1
            fixed_edges.append((u, v))
            fixed_edges.append((v, u))


def __fix_node_cpu(G):
    for node in G.nodes():
        cpu = __get_random_cpu()
        G.nodes[node]['cpu'] = cpu


def __compute_delay_for_link(G, n1, n2):
    """
    This implementation is based on B-JointSPs implementation which can be found on
    https://github.com/CN-UPB/B-JointSP/blob/master/src/bjointsp/read_write/reader.py
    :n1: the starting point of the edge
    :n2: the ending point of the edge
    :return: the delay based on the latitude and longitude
    """
    SPEED_OF_LIGHT = 299792458  # meter per second
    PROPAGATION_FACTOR = 0.77  # https://en.wikipedia.org/wiki/Propagation_delay

    if "Latitude" in G.nodes[n1]:
        n1_lat, n1_long = G.nodes[n1]['Latitude'], G.nodes[n1]['Longitude']
        n2_lat, n2_long = G.nodes[n2]['Latitude'], G.nodes[n2]['Longitude']
    elif "graphics" in G.nodes[n1]:
        n1_lat, n1_long = G.nodes[n1]['graphics']['y'], G.nodes[n1]['graphics']['x']
        n2_lat, n2_long = G.nodes[n2]['graphics']['y'], G.nodes[n2]['graphics']['x']
    elif "x" in G.nodes[n1]:
        n1_lat, n1_long = G.nodes[n1]['y'], G.nodes[n1]['x']
        n2_lat, n2_long = G.nodes[n2]['y'], G.nodes[n2]['x']
    else:
        raise ValueError("Not enough data in nodes")
    distance = vincenty((n1_lat, n1_long), (n2_lat, n2_long)).meters  # in meters
    delay = (distance / SPEED_OF_LIGHT * 1000) * PROPAGATION_FACTOR  # in milliseconds
    return delay


def __get_random_rate(seed):
    rnd.seed(seed)
    return rnd.randint(max_rate_lb, max_rate_ub)


def __get_random_cpu():
    return rnd.randint(cpu_lb, cpu_ub)
