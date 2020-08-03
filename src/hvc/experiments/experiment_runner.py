import itertools

import experiments.experiment_conducter as ec


def conduct_experiments(eval_key, conn, method="full_expansion"):
    """
    Starts conducting experiments until all are done
    :param eval_key: evaluation suffix
    :param conn: db connection containing the tables
    :param method: either "full_expansion", "one_path" or "two_paths"
    :return:
    """
    hierarchy_table = "hierarchies_{}".format(eval_key)
    graphs_table = "graphs_{}".format(eval_key)
    vnf_requests_table = "vnf_requests_{}".format(eval_key)
    seeds_table = "seeds_{}".format(eval_key)
    results_table = "results_{}".format(eval_key)

    vnf_desc_path = "/upb/departments/pc2/users/m/mirkoj/general/vnf_input/final_vnf_descriptions.yaml".format(eval_key)
    chains_path = "/upb/departments/pc2/users/m/mirkoj/general/vnf_input/final_chains.yaml".format(eval_key)

    cursor = conn.cursor()

    cursor.execute("SELECT hierarchy_id FROM {} WHERE hierarchy_id > 1".format(hierarchy_table))
    hierarchy_ids = [res[0] for res in cursor.fetchall()]
    cursor.execute("SELECT vnf_requests_id FROM {} WHERE request_count::int < 6".format(vnf_requests_table))
    request_ids = [res[0] for res in cursor.fetchall()]
    cursor.execute("SELECT graph_id FROM {}".format(graphs_table))
    graph_ids = [res[0] for res in cursor.fetchall()]
    cursor.execute("SELECT seed_id FROM {}".format(seeds_table))
    seed_ids = [res[0] for res in cursor.fetchall()]

    output_path = "/upb/departments/pc2/users/m/mirkoj/{}".format(eval_key)

    for hierarchy_id, request_id, graph_id, seed_id in itertools.product(hierarchy_ids, request_ids, graph_ids,
                                                                         seed_ids):
        ec.conduct_experiment(seed_id=seed_id, seed_table=seeds_table, hierarchy_id=hierarchy_id,
                              hierarchy_table=hierarchy_table, vnf_request_id=request_id,
                              vnf_request_table=vnf_requests_table, results_table=results_table,
                              chains_path=chains_path, vnf_descriptions_path=vnf_desc_path, graphml_id=graph_id,
                              graphml_table=graphs_table, output_path=output_path, conn=conn, method=method)
        conn.commit()

    cursor.close()
