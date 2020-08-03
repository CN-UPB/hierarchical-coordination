# Hierarchical Network and Service Coordination

An approach for hierarchical network and service coordination. Combines the best of two worlds: High solution quality, typically known from centralized approaches, and fast execution, known from distributed approaches. By splitting the network into hierarchies and domains, coordination can be parallelized but is still coordinated between domains.

This repository contains the MILP implementation using Gurobi as well as auxiliary tools.

## Setup

Requires Python 3.6+ and Gurobi. Dependencies can be installed with

```python
python setup.py install
```

## Usage

Please note that for using the optimization system, it is required to have Gurobi at version 8.11 installed on your system.
Please refer to the official documentation for instructions.

If you have defined your VNF chains, described your VNFs, defined a hierarchy for a network 
and defined a set of VNF requests, you can call the GML API to solve your problem hierarchically

```
import hvc.api.graph_ml as gml

gml.solve_graphml_model(graphml_path="tests/testfiles/graph_ml_scenario_1/input/atlanta_extended.gml",
vnf_description_path="tests/testfiles/graph_ml_scenario_1/input/vnf_descriptions.yaml",
chain_description_path="tests/testfiles/graph_ml_scenario_1/input/chains.yaml",
vnf_request_description_path="tests/testfiles/graph_ml_scenario_1/input/vnf_requests.yaml",
hierarchy_path="tests/testfiles/graph_ml_scenario_1/input/hierarchy.yaml",
output_path="./output",
solution_path="./solution"
method="full_expansion")
```
The api will then create intra-domain paths based on your hierarchy and VNF requests and will
hierarchically solve the problems in a top-down manner.

The `method` parameter specifies which method of path generation should be used. Three values are possible, "full_expansion", "one_path" or "two_paths. Using "one_path", for example, results in a faster optimization problem but allows less requests to be placed.

The `output_path` parameter specifies where the API will dump its intermediate problem inputs and outputs.
Such a folder always looks like this,


    .
    ├── childCoordinator1             # All input and output files of the
    │                                childCoordinator1
    ├── childCoordinator2             # All input and output files of the
    │                                 childCoordinator2
    ├── childCoordinator3             # All input and output files of the
    │                                 childCoordinator3
    ├── fullgraph.dot                 # A dot file describing the input graph
    ├── graph.dot                     # A dot file describing the
    │                                 extended coordinator network
    │                                 used by this coordinator
    ├── full_solution.log             # The complete MILP solution of this
    │                                 hierarchy
    ├── solution.log                  # The relevant parts of the MILP
    │                                 solution
    ├── advertised_restrictions.yaml  # All advertised restrictions of the
    │                                 child coordinators
    ├── chains.yaml                   # All chains used
    ├── network_description.yaml      # A description of the extended
    │                                 coordinator network
    ├── request_mappings.yaml         # Intermediate file that the coordinator
    │                                 uses to map the generated child
    │                                 VNF requests to its own request
    ├── vnf_descriptions.yaml         # All used VNFs
    └── vnf_requests.yaml             # The given VNF requests

The folders of the child coordinators, thereby, look exactly like the folder above (excluding the `fullgraph.dot` file).

As it is complicated to read the final solution of the hierarchical VNF chaining problem from the MILP output, the API will conveniently create a folder under the specified `solution_path`.
    
    .
    ├── ending_times.yaml         # Ending timestamp of each coordinator
    ├── overlay_solution.yaml     # Specifies the placements of VNFs to
    │                             substrate nodes and the traffic of the
    │                             VNF request arcs to the substrate edges
    ├── starting_times.yaml       # Starting timestamp of each coordinator
    └── time_delta.yaml           # Time in ms of each coordinator

Often only some metrics of the solution are of interest. Thus by calling the `result_interpreter` interface the overlay solution can be interpreted.

```
import hvc.experiments.result_interpreter as ri

placements, total_delay_map, end2end_delay_map, solving_time = interpret_results(graphml_path="tests/testfiles/graph_ml_scenario_1/input/atlanta_extended.yaml",
                                                                                 vnf_requests_path="tests/testfiles/graph_ml_scenario_1/input/vnf_requests.yaml",
                                                                                 hierarchy_path="tests/testfiles/graph_ml_scenario_1/input/hierarchy.yaml",
                                                                                 solution_path="./solution",
                                                                                 chains_path="tests/testfiles/graph_ml_scenario_1/input/chains.yaml")
```

It calculates the total amount of VNF placements, a map mapping each request to its total delay, a map mapping each request to its wort case end-to-end delay and the total solving time.

### Creating hierarchies
As described in the thesis, k-Means can be used to derive hierarchies. Using the data_generator api a hierarchy that has 4 coordinators on level k=2 and 2 coordinators on level k=3 can be generated by calling

```
import hvc.experiments.data_generator as dg

dg.build_hierarchy(graph_input="tests/testfiles/graph_ml_scenario_1/input/atlanta_extended.yaml",
                   hierarchy_output="./hierarchy.yaml",
                   clusters_per_hierarchy=[4, 2]
                   seed=0)
```
### Creating own requests

Each request is described in the `vnf_requests.yaml` file. 
```
request1:                 # Name of the request (do not use underscores!)
  egress: N11             # identifier of the substrate node which is the egress
  ingress: N5             # identifier of the substrate node which is the ingress
  initial_rate: 2         # initial rate of the request
  vnf_chain: chain1       # identifier of the requested chain
```

### Creating own chains

The `chains.yaml` file specifies all chains in the system, since every chain is linear it is described using python tuples.
A chain must start with the `SRC` component and must end with the `DST` component. Each used component must be a correctly described VNF according to the `vnf_descriptions.yaml` file
```
chain1:
  - !!python/tuple
    - SRC
    - A
  - !!python/tuple
    - A
    - B
  - !!python/tuple
    - B
    - DST
```
### Creating own VNFs
As each VNF/component is described by two functions which are described using lambdas (needless to say that you should not use this in production as you are allowing the user to allow arbitrary code here...).

```
cpu_consumption:
  A: 'lambda in_rate: 0.5 * in_rate'
  B: 'lambda in_rate: 0.3 * in_rate'
  DST: 'lambda in_rate: 0'
  SRC: 'lambda in_rate: 0'
outgoing_rate:
  A: 'lambda in_rate: 1.5 * in_rate'
  B: 'lambda in_rate: 1.3 * in_rate'
  DST: 'lambda in_rate: in_rate'
  SRC: 'lambda in_rate: in_rate'
vnfs:
  - SRC
  - A
  - B
  - DST
```
 The fields are pretty much self-explanatory. Please do not use non-linear functions as they will result in Gurobi errors or live-locks during the result-interpreting phase (refer to Section 3.4 such functions cannot be inverted using the described trick).

### Using a different graph
This implementation has two example graphs in the example input folder. When you want to use your own gm graph, please note that the following restrictions apply.

  * The graph has to be directed and bidirectional
  * Each edge needs an 'id', 'max_rate' and 'delay' field
  * Each node needs a 'cpu' field
  * Please order your edges, i.e. if u -> v has id '0' then let v -> u have id '1'

Additionally, if you want to cluster your graph using the k-Means api, your node needs a 'Latitude' and 'Longitude' field to derive the geo location.

### Understanding the networks
It is in some cases interesting to see how exactly the advertised paths look like, which nodes are border nodes, etc. To this end, each hierarchy describes it used extended coordinator network in a file called `graph.dot` using the DOT graph description language. Please refer to the official graphviz documentation to see how such files can be converted into PNGs.

## Development
If you want to use the MILP implementation independently of the path generation, please refer to the `gurobipy_mip` interface.
Two methods are convenient: `get_model` will generate the model and return it such that additional restrictions can be added by the user and `solve_model` will solve the model.

Please refer to the `gurobipy_test.py` to see example inputs to these methods.

## Contributors

* Development: [@mirkojuergens](https://github.com/mirkojuergens)
* Advisor: [@stefanbschneider](https://github.com/stefanbschneider)

Please use GitHub's issue system to file bugs or ask questions.