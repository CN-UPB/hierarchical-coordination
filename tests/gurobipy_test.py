from gurobipy import GRB

import src.hvc.mip.gurobipy_mip as gmip
from src.hvc.mip.utils import pretty_print_solution


def test_scenario_1():
    network_description_file = "testfiles/scenario_1/network_description.yaml"
    vnf_description_file = "testfiles/scenario_1/vnf_descriptions.yaml"
    chain_description_file = "testfiles/scenario_1/chains.yaml"
    advertised_restriction_file = "testfiles/scenario_1/advertised_restrictions.yaml"
    vnf_request_description_file = "testfiles/scenario_1/vnf_requests.yaml"
    parameters, indices, decision_vars, model = gmip.solve_model(network_description_file=network_description_file,
                                                                 chain_description_file=chain_description_file,
                                                                 vnf_description_file=vnf_description_file,
                                                                 vnf_request_description_file=vnf_request_description_file,
                                                                 advertised_restriction_file=advertised_restriction_file,
                                                                 pretty_print=True)
    # make sure that there are only two placed VNFs
    # however for each ingress and each egress there is a placement aswell
    all_ingresses = [request["ingress"] for request in parameters.vnf_requests.values()]
    all_egresses = [request["egress"] for request in parameters.vnf_requests.values()]
    num_ingress_egress_nodes = len(set(all_ingresses)) + len(set(all_egresses))

    assert sum(decision_vars.gamma[vnf, path].X for vnf in indices.vnfs for path in
               indices.paths) == 2 + num_ingress_egress_nodes


# just a single request but the inter domain edge e1 has such a huge delay that the request has to be routed over e2
# also it is by the cpu restrictions of v3 and v5 impossible to place both VNFs on one path
# thus A has to be placed on p2 and B has to be placed on p4
def test_scenario_2():
    network_description_file = "testfiles/scenario_2/network_description.yaml"
    vnf_description_file = "testfiles/scenario_2/vnf_descriptions.yaml"
    chain_description_file = "testfiles/scenario_2/chains.yaml"
    advertised_restriction_file = "testfiles/scenario_2/advertised_restrictions.yaml"
    vnf_request_description_file = "testfiles/scenario_2/vnf_requests.yaml"

    parameters, indices, decision_vars, model = gmip.get_model(network_description_file=network_description_file,
                                                               chain_description_file=chain_description_file,
                                                               vnf_description_file=vnf_description_file,
                                                               vnf_request_description_file=vnf_request_description_file,
                                                               advertised_restriction_file=advertised_restriction_file,
                                                               with_delay_constraints=False,
                                                               generate_backward_paths=False)
    #   pretty_print=True)

    # model.addConstr(decision_vars.gamma["B", "p4"] == 1.0)
    # model.addConstr(decision_vars.gamma["A", "p2"] == 1.0)
    model.optimize()
    pretty_print_solution(indices=indices, decision_variables=decision_vars, model=model)

    # check if there are only two placements(+ SRC and DST placement):
    assert sum(
        decision_vars.gamma[vnf, path].X for vnf in indices.vnfs for path in indices.paths) == 2 + 2

    # check if A is placed on p2 and B on p4
    assert decision_vars.gamma["A", "p2"].X + decision_vars.gamma["A", "p1"].X == 1.0
    assert decision_vars.gamma["B", "p4"].X + decision_vars.gamma["B", "p3"].X == 1.0


# same test as scenario 2 but now we force the MIP to place A on p4 and use it with 5 GB/s
# thus, the MIP should find no solution here!
def test_scenario_2_fail():
    network_description_file = "testfiles/scenario_2/network_description.yaml"
    vnf_description_file = "testfiles/scenario_2/vnf_descriptions.yaml"
    chain_description_file = "testfiles/scenario_2/chains.yaml"
    advertised_restriction_file = "testfiles/scenario_2/advertised_restrictions.yaml"
    vnf_request_description_file = "testfiles/scenario_2/vnf_requests.yaml"

    parameters, indices, decision_vars, model = gmip.get_model(network_description_file=network_description_file,
                                                               chain_description_file=chain_description_file,
                                                               vnf_description_file=vnf_description_file,
                                                               vnf_request_description_file=vnf_request_description_file,
                                                               advertised_restriction_file=advertised_restriction_file)
    a_placement = model.addConstr(decision_vars.gamma["A", "p4"] == 1.0)
    a_inrate = model.addConstr(decision_vars.sigma_in["A", "p4"] == 5.0)
    model.optimize()
    pretty_print_solution(indices=indices, decision_variables=decision_vars, model=model)
    assert model.Status == GRB.OPTIMAL


# two chains: A -> B and just C
# p1 and p2 share all cpus
# C has huge CPU demand
# p3 has massive CPU resources but is bottlenecked by e1 that can only forward 100 GBs (all the demand of C)
# the only possible solution for the MIP is thus to place A on p2 B on p4 and C on p3
def test_scenario_3():
    network_description_file = "testfiles/scenario_3/network_description.yaml"
    vnf_description_file = "testfiles/scenario_3/vnf_descriptions.yaml"
    chain_description_file = "testfiles/scenario_3/chains.yaml"
    advertised_restriction_file = "testfiles/scenario_3/advertised_restrictions.yaml"
    vnf_request_description_file = "testfiles/scenario_3/vnf_requests.yaml"

    parameters, indices, decision_vars, model = gmip.solve_model(network_description_file=network_description_file,
                                                                 chain_description_file=chain_description_file,
                                                                 vnf_description_file=vnf_description_file,
                                                                 vnf_request_description_file=vnf_request_description_file,
                                                                 advertised_restriction_file=advertised_restriction_file,
                                                                 pretty_print=False)
    assert decision_vars.gamma["A", "p2"].X == 1.0
    assert decision_vars.gamma["B", "p4"].X == 1.0
    assert decision_vars.gamma["C", "p3"].X == 1.0


# one chain: just A
# however A has such a huge out-rate that it is impossible to place it on p1 or p2 as e1 or e2 cannot cover the rate
def test_scenario_4():
    network_description_file = "testfiles/scenario_4/network_description.yaml"
    vnf_description_file = "testfiles/scenario_4/vnf_descriptions.yaml"
    chain_description_file = "testfiles/scenario_4/chains.yaml"
    advertised_restriction_file = "testfiles/scenario_4/advertised_restrictions.yaml"
    vnf_request_description_file = "testfiles/scenario_4/vnf_requests.yaml"

    parameters, indices, decision_vars, model = gmip.solve_model(network_description_file=network_description_file,
                                                                 chain_description_file=chain_description_file,
                                                                 vnf_description_file=vnf_description_file,
                                                                 vnf_request_description_file=vnf_request_description_file,
                                                                 advertised_restriction_file=advertised_restriction_file,
                                                                 pretty_print=True)

    assert decision_vars.gamma["A", "p3"].X + decision_vars.gamma["A", "p4"].X == 1.0
    assert decision_vars.gamma["A", "p1"].X + decision_vars.gamma["A", "p2"].X == 0.0
