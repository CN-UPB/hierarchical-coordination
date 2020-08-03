"""
Adaption of the official networkx implementation at:
https://github.com/networkx/networkx/blob/master/networkx/algorithms/flow/edmondskarp.py

"""

import logging

import networkx as nx
from networkx.algorithms.flow.utils import build_residual_network

from hvc.mip import utils

logger = utils.setup_logger('ek', "edmonds_karp.log", logging.INFO)


def edmonds_karp_core(R, s, t, cutoff, is_lowest_hierarchy, routing_restrictions, G):
    """
    Implementation of the Edmonds-Karp algorithm.
    """
    R_nodes = R.nodes
    R_pred = R.pred
    R_succ = R.succ

    path_map = {}
    #Since the edmonds karp algorithm transformed a directed graph into an undirected graph,
    # the path map keeps track which directed edges were used to deduce the undirected graph
    if not is_lowest_hierarchy:
        for (u, v) in G.edges():
            if (u, v) not in path_map.values():
                path_map[G[u][v]["label"]] = (u, v)
                G[u][v]['id'] = G[u][v]["label"]

    inf = R.graph['inf']

    def augment(path):
        """
        Augment flow along a path from s to t.
        """
        # Determine the path residual capacity.
        flow = inf
        it = iter(path)
        u = next(it)
        for v in it:
            attr = R_succ[u][v]
            flow = min(flow, attr['capacity'] - attr['flow'])
            u = v
        if flow * 2 > inf:
            raise nx.NetworkXUnbounded(
                'Infinite capacity path, flow unbounded above.')
        # Augment flow along the path.
        it = iter(path)
        u = next(it)
        for v in it:
            R_succ[u][v]['flow'] += flow
            R_succ[v][u]['flow'] -= flow
            u = v
        if not is_lowest_hierarchy:
            logger.debug("Trying to resolve the routing restrictions")
            path_set = set()
            it = iter(path)
            u = next(it)
            for v in it:
                if u == "super_ingress" or v == "super_egress":
                    u = v
                    continue
                # translate the tuple to a path identifier via the path map
                path_id = next((path_key for path_key, p in path_map.items() if p == (u, v) or p == (v, u)), None)
                logger.debug("Path {} resolves to path id {}".format((u, v), path_id))
                if path_id == None:
                    continue
                if path_map[path_id] == (u, v):
                    path_set.add(path_id)
                else:
                    logger.debug(
                        "Conflict! edge {} was added as {}. Trying to deduce the path heuristically.".format((u, v),
                                                                                                             (v, u)))
                    path_id = utils.get_backward_edge_id(forward_edge_id=path_id)
                    logger.debug("Resolved {} to {}".format((v, u), path_id))
                    path_set.add(path_id)
                u = v

            logger.debug("Edmonds karp found a new path: {} with flow: {}".format(path, flow))
            for routing_restriction in routing_restrictions:
                intersection = set(routing_restriction.paths) & path_set
                if len(intersection) > 2:
                    logger.warn(
                        "Panic! The path {0} contains paths {1}, which are part of the same routing restriction {2}."
                        "Hence, they use the same bottleneck. The flow will be reduced now.".format(path_set,
                                                                                                    intersection,
                                                                                                    routing_restriction.identifier))
                    raise RuntimeError()
                for path_id in path_set:
                    if path_id in routing_restriction.paths:
                        intersection = set(routing_restriction.paths) & set(path_map.keys())
                        logger.debug("Path {} was part of the routing restriction {}.".format(path_id,
                                                                                              routing_restriction.identifier))
                        logger.debug("Thus, the flow of paths {} will be reduced by {}".format(intersection, flow))
                        for p_prime in intersection:
                            if path_id != p_prime:
                                (src, dst) = path_map[p_prime]
                                logger.debug("Edge {} will be charged with {} cap".format((src, dst), flow))
                                R_succ[src][dst]['capacity'] = max(R_succ[src][dst]['capacity'] - flow, 0)
                                logger.debug("New flow of edge {} is {}".format((src, dst), R_succ[src][dst]['capacity']))

        return flow

    def bidirectional_bfs():
        """
        Bidirectional breadth-first search for an augmenting path.
        """
        pred = {s: None}
        q_s = [s]
        succ = {t: None}
        q_t = [t]
        while True:
            q = []
            if len(q_s) <= len(q_t):
                for u in q_s:
                    for v, attr in R_succ[u].items():
                        # no circle and there is capacity left on the edge
                        if v not in pred and attr['flow'] < attr['capacity']:
                            logger.debug("{} is a valid succ of {} with flow {} and cap {}".format(v, u, attr['flow'],
                                                                                                  attr['capacity']))
                            pred[v] = u
                            if v in succ:
                                return v, pred, succ
                            q.append(v)
                if not q:
                    return None, None, None
                q_s = q
            else:
                for u in q_t:
                    for v, attr in R_pred[u].items():
                        if v not in succ and attr['flow'] < attr['capacity']:
                            logger.debug("{} is a valid succ of {} with flow {} and cap {}".format(u, v, attr['flow'],
                                                                                                  attr['capacity']))
                            succ[v] = u
                            if v in pred:
                                return v, pred, succ
                            q.append(v)
                if not q:
                    return None, None, None
                q_t = q

    # Look for shortest augmenting paths using breadth-first search.
    flow_value = 0
    paths = []
    while flow_value < cutoff:
        v, pred, succ = bidirectional_bfs()
        if pred is None:
            break
        path = [v]
        # Trace a path from s to v.
        u = v
        while u != s:
            u = pred[u]
            path.append(u)
        path.reverse()
        # Trace a path from v to t.
        u = v
        while u != t:
            u = succ[u]
            path.append(u)
        flow = augment(path)
        flow_value += flow
        paths.append((path, flow))

    return flow_value, paths


def edmonds_karp_impl(G, s, t, capacity, residual, cutoff, level, routing_restrictions):
    """
    Implementation of the Edmonds-Karp algorithm.
    """
    if s not in G:
        raise nx.NetworkXError(f"node {str(s)} not in graph")
    if t not in G:
        raise nx.NetworkXError(f"node {str(t)} not in graph")
    if s == t:
        raise nx.NetworkXError('source and sink are the same node')

    if residual is None:
        R = build_residual_network(G, capacity)
    else:
        R = residual

    # Initialize/reset the residual network.
    for u in R:
        for e in R[u].values():
            e['flow'] = 0

    if cutoff is None:
        cutoff = float('inf')
    R.graph['flow_value'], paths = edmonds_karp_core(R, s, t, cutoff, level, routing_restrictions, G)

    return R, paths


def edmonds_karp(G, s, t, capacity='capacity', residual=None, value_only=False,
                 cutoff=None, is_lowest_hierarchy=True, routing_restrictions=None):
    logger.debug("Edmonds Karp path computation for G with nodes {} and edges {} started.".format(G.nodes(), G.edges()))
    R, paths = edmonds_karp_impl(G, s, t, capacity, residual, cutoff, is_lowest_hierarchy, routing_restrictions)
    R.graph['algorithm'] = 'edmonds_karp'
    return R, paths
