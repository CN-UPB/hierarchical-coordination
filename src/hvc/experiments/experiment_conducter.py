import os
from statistics import mean

import hvc.api.graphml as gml
import hvc.experiments.result_interpreter as ri


def conduct_experiment(seed_id, seed_table, hierarchy_id, hierarchy_table, graphml_id, graphml_table, vnf_request_id,
                       vnf_request_table, results_table, chains_path, vnf_descriptions_path, output_path, conn,
                       method="full_expansion", use_placements=-1):
    """
    Starts an experiment run for the given parameters, each parameter is specified by a table and an id
    :param seed_id:
    :param seed_table:
    :param hierarchy_id:
    :param hierarchy_table:
    :param graphml_id:
    :param graphml_table:
    :param vnf_request_id:
    :param vnf_request_table:
    :param results_table:
    :param chains_path: the path of the chain description file
    :param vnf_descriptions_path: the path of the vnf_description file
    :param output_path: the path where the output of this run should be saved to
    :param conn: db connection which has all of the above tables
    :param method: either "full_expansion", "one_path" or "two_paths"
    :param use_placements: if the amount of placements should be fixed (careful: only makes sense in flat hierarchies!)
    :return:
    """
    cursor = conn.cursor()

    # obtain the parameters specified by the ids
    cursor.execute("SELECT {} FROM {} WHERE seed_id={}".format("seed", seed_table, seed_id))
    seed = cursor.fetchone()[0]
    cursor.execute("SELECT {} FROM {} WHERE hierarchy_id={}".format("hierarchy_path", hierarchy_table, hierarchy_id))
    hierarchy_path = cursor.fetchone()[0]
    cursor.execute("SELECT {} FROM {} WHERE graph_id={}".format("graph_path", graphml_table, graphml_id))
    graphml_path = cursor.fetchone()[0]
    cursor.execute(
        "SELECT {} FROM {} WHERE vnf_requests_id={}".format("vnf_requests_path", vnf_request_table, vnf_request_id))
    vnf_requests_path = cursor.fetchone()[0]

    insert_cmd = "INSERT INTO {} (method, seed_id, hierarchy_id, graph_id, vnf_requests_id) VALUES" \
                 " ('{}','{}','{}','{}','{}') RETURNING experiment_id".format(
        results_table, method, seed_id, hierarchy_id, graphml_id, vnf_request_id)

    if use_placements == -1:
        get_exisiting_cmd = "SELECT experiment_id FROM {} WHERE method='{}' AND seed_id='{}' AND" \
                            " hierarchy_id='{}' AND graph_id='{}' AND vnf_requests_id='{}'".format(
            results_table, method, seed_id, hierarchy_id, graphml_id, vnf_request_id)
    else:
        get_exisiting_cmd = "SELECT experiment_id FROM {} WHERE method='{}' AND seed_id='{}' AND" \
                            " hierarchy_id='{}' AND graph_id='{}' AND vnf_requests_id='{}' AND placements='{}'".format(
            results_table, method, seed_id, hierarchy_id, graphml_id, vnf_request_id, use_placements)

    # first check whether this experiment has already been conducted
    cursor.execute(get_exisiting_cmd)
    if cursor.rowcount >= 1:
        # experiment already conducted
        return

    print("Started conducting experiments with request id {} ; hierarchy id {}; graph id {}; seed id {}".format(
        vnf_request_id, hierarchy_id, graphml_id, seed_id))

    # now enter an empty experiment to prevent any other conducter from starting the same experiment!
    cursor.execute(insert_cmd)
    conn.commit()
    experiment_id = cursor.fetchone()[0]
    print("Successfully obtained experiment id {}".format(experiment_id))

    if not os.path.exists(output_path):
        os.mkdir(output_path)

    output_path = "{}/experiment_{}".format(output_path, experiment_id)

    if not os.path.exists(output_path):
        os.mkdir(output_path)

    # solve the experiment
    try:
        gml.solve_graphml_model(graphml_path=graphml_path,
                                vnf_description_path=vnf_descriptions_path,
                                chain_description_path=chains_path,
                                vnf_request_description_path=vnf_requests_path,
                                output_path="{0}/output".format(output_path),
                                hierarchy_path=hierarchy_path,
                                solution_path="{0}/solution".format(output_path),
                                seed=seed, use_exact_placements=use_placements, path_aggregation=method)
    except AttributeError:
        insert_results_cmd = "UPDATE {} SET placements='{}' WHERE experiment_id={}".format(
            results_table, "INFEASIBLE", experiment_id)

        cursor.execute(insert_results_cmd)
        return

    # interpret the results
    placements, total_delay_map, end2end_delay_map, solving_time = ri.interpret_results(graphml_path=graphml_path,
                                                                                        vnf_requests_path=vnf_requests_path,
                                                                                        hierarchy_path=hierarchy_path,
                                                                                        chains_path=chains_path,
                                                                                        solution_path="{0}/solution".format(
                                                                                            output_path))

    avg_total_delay = mean(list(total_delay_map.values()))
    avg_e2e_delay = mean(list(end2end_delay_map.values()))

    sum_total_dealy = sum(list(total_delay_map.values()))
    sum_e2e_delay = sum(list(end2end_delay_map.values()))

    insert_results_cmd = "UPDATE {} SET placements={}, runtime={}, avg_total_delay={}, avg_e2e_delay={}," \
                         " sum_total_delay={}, sum_e2e_delay={} WHERE experiment_id={}".format(
        results_table, placements, solving_time, avg_total_delay, avg_e2e_delay, sum_total_dealy, sum_e2e_delay,
        experiment_id)
    # update the results
    cursor.execute(insert_results_cmd)
    conn.commit()

