Judge whether this document is relevant to computer science: the study, design, analysis,
implementation, or evaluation of computational algorithms, software, programming languages,
computer systems, networks, security, artificial intelligence, human-computer interaction,
robotics software, embedded systems, or quantum computing.

Definitions (as used in this context):

- Computer science: the technical study of computation and of systems that represent,
  process, store, communicate, secure, or interact with information.
- Computational method: an algorithmic or software method whose design, behavior,
  correctness, complexity, implementation, or performance is substantively examined.
  Merely calculating a result or running existing software does not qualify.
- Computer system: programmable hardware and software considered through its architecture,
  operating behavior, resource management, performance, reliability, or interaction with
  other systems or users.
- Software contribution: a substantive design, implementation, analysis, testing, repair,
  maintenance, or evaluation contribution concerning software itself. A script or software
  package used only as a tool for another field is not a software contribution.
- Algorithmic contribution: a new or substantively analyzed procedure, model, data
  structure, optimization technique, or learning method. Applying a standard algorithm
  without examining the algorithm or computing problem is not an algorithmic contribution.
- Technical evaluation: evaluation of properties such as correctness, accuracy,
  generalization, complexity, latency, throughput, memory use, scalability, robustness,
  security, usability, or accessibility. Reporting only a scientific or business outcome
  produced by software is not a technical computing evaluation.

THE CORE TEST - apply this first, before anything else. A document is RELEVANT only if BOTH
are true:

1. COMPUTER-SCIENCE SUBJECT: it substantively involves at least one in-scope computer-science
   topic listed below, AND
2. COMPUTING SUBSTANCE: it substantively studies, designs, analyzes, implements, evaluates,
   or explains a computational method, software artifact, or computer system. The computing
   must be part of what the document is about, not merely a tool, keyword, dataset, analogy,
   or application detail.

If either condition is missing, weak, or only mentioned in passing, the document is NOT
relevant (mark `maybe` or `irrelevant` according to the scoring rules below).
**Do not judge relevance from isolated keywords.**

IN-SCOPE COMPUTER-SCIENCE TOPICS

Algorithms and theory:
- algorithm design and analysis; data structures; graph, sorting, search, string,
  approximation, randomized, online, parallel, and distributed algorithms
- greedy methods, dynamic programming, divide and conquer, branch and bound,
  computational geometry, combinatorial optimization, shortest paths, and network flow
- computational complexity, complexity classes, NP-hardness and NP-completeness,
  parameterized complexity, computability, automata, formal languages, Turing machines,
  lambda calculus, type theory, logic, satisfiability, SAT, and SMT
- formal methods, proof assistants, automated theorem proving, model checking, program
  verification, program semantics, temporal logic, and Hoare logic

Programming languages and compilers:
- language design and semantics; type systems and inference; functional, object-oriented,
  logic, concurrent, and domain-specific programming languages
- compilers, interpreters, virtual machines, intermediate representations, parsing, code
  generation, optimization, register allocation, runtime systems, and garbage collection
- static, data-flow, control-flow, source-code, bytecode, and binary analysis; memory safety

Operating systems and storage:
- kernels, system calls, processes, threads, scheduling, synchronization, concurrency,
  deadlocks, race conditions, and lock-free or wait-free algorithms
- virtual memory, allocation, address spaces, memory protection, persistent memory, file
  systems, storage systems, device drivers, containers, and operating-system virtualization

Computer architecture and high-performance computing:
- processors, instruction sets, microarchitecture, multicore and manycore systems,
  out-of-order execution, branch prediction, caches, coherence, prefetching, and memory
  consistency
- GPUs, FPGAs, ASICs, accelerators, heterogeneous systems, parallel and high-performance
  computing, clusters, MPI, shared-memory programming, profiling, and performance modeling

Software engineering:
- requirements, architecture, design, development processes, maintenance, evolution,
  modernization, refactoring, program comprehension, repository mining, and technical debt
- defect prediction, bug and fault localization, automated repair, unit and integration
  testing, regression and property-based testing, fuzzing, and test automation
- version control, configuration management, continuous integration and delivery, DevOps,
  APIs, microservices, software product lines, and open-source software engineering

Databases and information systems:
- relational, distributed, parallel, in-memory, cloud, NoSQL, graph, document, key-value,
  and column-oriented databases
- transactions, isolation, query processing and optimization, indexing, schemas, data
  warehouses and lakes, stream processing, provenance, integration, and data cleaning
- information retrieval, search engines, ranking, recommender systems, knowledge graphs,
  and the semantic web

Distributed systems and cloud computing:
- consensus, replication, fault tolerance, Byzantine fault tolerance, distributed
  transactions, consistency models, remote procedure calls, and peer-to-peer systems
- cloud-native systems, virtual machines, containers, orchestration, serverless computing,
  resource scheduling, load balancing, edge and fog computing, grids, distributed ledgers,
  blockchain protocols, and smart contracts

Computer networks and Internet systems:
- network architectures, stacks and protocols; routing, transport, congestion control,
  packet scheduling and switching, quality of service, DNS, BGP, and multipath transport
- software-defined networking, network-function virtualization, content-delivery and data
  center networks, wireless sensor and ad hoc networks, network measurement, telemetry,
  simulation, performance, and traffic analysis
- Internet of Things and machine-to-machine communication when the networking or computing
  system is substantively studied

Security, privacy, and cryptography:
- computer, information, network, software, systems, application, web, mobile, cloud,
  database, operating-system, hardware, and usable security
- access control, authentication, authorization, identity, intrusion detection, malware,
  ransomware, vulnerabilities, exploitation, injection, side channels, denial of service,
  exploit mitigation, and digital forensics
- differential privacy, privacy-preserving computation, secure multiparty computation,
  homomorphic encryption, public-key and post-quantum cryptography, and zero-knowledge proofs

Artificial intelligence and natural language processing:
- artificial intelligence, machine learning, deep and representation learning; supervised,
  unsupervised, semi-supervised, self-supervised, reinforcement, federated, transfer,
  continual, and few-shot learning
- neural networks, transformers, foundation and large language models, generative and
  diffusion models, decision trees, support vector machines, Bayesian and probabilistic
  graphical models
- automated planning, knowledge representation, reasoning, multi-agent systems,
  explainable AI, adversarial machine learning, machine translation, speech processing,
  question answering, and information extraction

Computer vision, graphics, and visualization:
- image recognition, object detection, segmentation, tracking, pose estimation, scene
  understanding, reconstruction, structure from motion, and optical flow
- rendering, ray tracing, rasterization, geometric modeling, mesh processing, animation,
  virtual, augmented, and mixed reality
- multimedia systems, image and video compression, visual retrieval, information
  visualization, and scientific visualization as computing techniques or systems

Human-computer interaction:
- user interfaces, user experience, interaction design, user-centered and human-centered
  computing, interactive systems, and computer-supported cooperative work
- ubiquitous, pervasive, mobile, wearable, tangible, natural, brain-computer, eye-tracking,
  and gesture-based interfaces
- accessible and assistive computing, usability evaluation, human-robot interaction,
  social and collaborative computing, and crowdsourcing platforms

Robotics and autonomous-system software:
- robot operating systems, autonomous, mobile, humanoid, service, industrial, multi-robot,
  and swarm systems
- motion and path planning, navigation, localization, mapping, SLAM, perception, learning,
  manipulation, grasping, behavior planning, trajectory planning, and sensor fusion
- software and algorithms for self-driving vehicles and unmanned aerial vehicles

Emerging, embedded, and real-time computing:
- quantum computers, algorithms, circuits, programming, error correction, and software
- embedded software and systems, firmware, microcontrollers, real-time operating systems,
  cyber-physical and safety-critical systems
- approximate, in-memory, reconfigurable, neuromorphic, DNA, and optical computing, and
  edge intelligence

THE CONTRIBUTION / TOOL BOUNDARY - the hardest calls

Many fields use computers, code, statistics, simulation, optimization, databases, GIS,
machine learning, and visualization. Use does not by itself make a document computer science.
Apply these rules literally:

- IN: the document's subject includes the algorithm, software, interface, architecture,
  protocol, security property, computing theory, or computer-system behavior itself.
- OUT: established software or a standard method is used only to answer a biology,
  medicine, chemistry, physics, climate, engineering, social-science, business, or humanities
  question.
- IN: a technical survey, benchmark, replication study, dataset paper, or empirical study
  that substantively analyzes computer-science methods or systems.
- OUT: a dataset, database, website, dashboard, or mobile app is merely assembled or used,
  with no substantive computing design or evaluation.
- IN: an HCI or usable-security study can make a CS contribution through interaction design,
  usability, accessibility, or user behavior around a computing system; it need not propose
  a new algorithm.
- OUT: a study about people's opinions, health, purchasing, learning, or social behavior is
  not HCI merely because data were collected online or through an app.
- IN: robotics software, perception, planning, localization, and control algorithms.
- OUT: robot mechanics, vehicle dynamics, actuator materials, or mechanical design with no
  substantive computing contribution.

Use this removal test: **if the computational method or computer system were replaced by a
standard off-the-shelf tool and the document would still have the same research question and
contribution, computing is not substantive.**

INTERDISCIPLINARY AND APPLICATION-DOMAIN BOUNDARY

The following domains often contain substantial computation but are not automatically
computer science: computational biology and bioinformatics; biomedical, health, and medical
informatics; clinical decision support and medical imaging; computational neuroscience;
computational chemistry, physics, materials science, fluid dynamics, and finite-element
analysis; climate, weather, hydrological, ocean, seismic, and geophysical modeling; remote
sensing and GIS applications; computational social science and digital humanities; finance,
econometrics, marketing, and scientific bibliometrics; ecology; transportation, power, water,
building, and manufacturing applications.

Judge these documents as follows:

- If an existing computational method is only applied to produce domain knowledge or improve
  a domain outcome, score 0 / `irrelevant`.
- If the document makes a real, novel computational contribution but its primary objective,
  evaluation, and claims concern the application domain, score at most 1 / `maybe`. For
  example, a new image-segmentation model developed specifically to improve tumor delineation
  is `maybe`, not automatically irrelevant.
- If the central contribution is explicitly a generalizable computer-science method or system,
  and the application domain supplies only data, a benchmark, or one evaluation setting, it
  may score 2 or 3. Require clear evidence; do not infer generality from the use of AI alone.
- A document can combine computer science with another field and still be relevant, but the
  CS contribution must be independently identifiable and substantive.

Decision and score - these **MUST agree**. Choose the score first, then set `decision` from it:

- score 3 -> decision "relevant": Strongly relevant. An in-scope computer-science method,
  system, theory, or technical question is the central focus and principal contribution.
- score 2 -> decision "relevant": Relevant. Computer-science content is clear and substantive
  but shares the focus with a broader topic, or a generalizable computing method or system is
  substantively analyzed using an application domain as an evaluation setting.
- score 1 -> decision "maybe": Partial, borderline, or interdisciplinary. There is an
  identifiable substantive computing contribution, but it is thin, secondary, narrowly tied
  to an excluded application domain, or insufficiently distinguished from tool use.
- score 0 -> decision "irrelevant": No meaningful computer-science contribution or content;
  computing is absent, incidental, standard tool use, or only a passing mention.

**Never pair score 2 or 3 with "maybe" or "irrelevant"; score 1 with "relevant" or
"irrelevant"; or score 0 with "relevant" or "maybe".**

COMMON FALSE POSITIVES

Mark these IRRELEVANT unless the document explicitly makes a substantive computer-science
contribution:

- Papers that say "we used machine learning," "we wrote a program," or "we performed a
  simulation" but focus entirely on domain findings.
- Studies using standard regression, clustering, neural networks, optimization packages,
  statistical software, databases, cloud services, or high-performance computing as tools.
- Scientific simulations where the contribution is a biological, chemical, physical,
  atmospheric, hydrological, ecological, or engineering result rather than the computational
  method or system.
- Medical diagnosis, tumor segmentation, protein prediction, genomics, drug discovery, and
  clinical prediction papers whose claims concern health or biology rather than computing.
- Remote-sensing classification, GIS mapping, traffic forecasting, power-grid optimization,
  financial prediction, and social-network analysis that merely apply established methods.
- Pure mathematics, statistics, information theory, electrical engineering, control theory,
  mechanical robotics, or semiconductor device research with no substantive computing focus.
- Documents about online education, digital media, social media, electronic commerce, or
  information technology policy that do not study a computing artifact, system, or interaction.
- Words with unrelated meanings: "network" in biology or sociology, "architecture" in
  buildings, "memory" in psychology, "learning" in education or animals, "virus" in medicine,
  "cloud" in weather, "language" in linguistics, "security" in geopolitics, "model" in any
  field, or "program" meaning an organizational initiative.

IMPORTANT JUDGING GUIDANCE - follow these steps in order:

1. State what the document is actually about in one sentence, ignoring isolated keywords.
2. Identify the specific in-scope computer-science topic, if any.
3. Identify the computing substance: what method, artifact, system, theory, or technical
   property is designed, analyzed, implemented, evaluated, or explained?
4. Apply the contribution/tool removal test and the interdisciplinary boundary.
5. Assign the score, then set the decision to match.

Further guidance:

- **When uncertain between two scores, pick the LOWER one. Prefer precision (taking
  `relevant` as positive) over recall.**
- Judge only from the provided evidence. Sectionized text may omit references and details;
  **do not assume content that is not shown.**
- Terms such as "novel," "framework," "model," "architecture," "platform," and "intelligent"
  do not prove a computer-science contribution. Look for concrete technical substance.
- Using accuracy, precision, recall, or another model metric does not by itself establish CS
  relevance; standard model application can still be domain research.
- Implementation alone is not always enough. A routine domain-specific script, workflow, or
  interface with no technical analysis is irrelevant.
- A document need not contain source code or propose a new method. Theory, systems analysis,
  empirical software engineering, benchmarking, replication, HCI, security measurement, and
  substantive technical surveys can qualify.
- If only one weak sentence mentions a computing topic and the rest is unrelated, score 0.
- In the rationale, name the CS topic and computing contribution identified, or state that no
  substantive contribution was found.

Examples (decision / score / why):

- "A Linear-Time Approximation Algorithm for Dynamic Graph Matching"
  -> relevant / 3. Algorithm design and complexity analysis are the central contribution.
- "A Type System for Memory-Safe Concurrent Programming"
  -> relevant / 3. Programming-language theory, concurrency, and memory safety are central.
- "Byzantine Fault-Tolerant Consensus for Geo-Distributed Databases"
  -> relevant / 3. The protocol and distributed-system properties are the principal subject.
- "Usability and Error Recovery in Screen Readers for Mobile Interfaces"
  -> relevant / 3. Accessibility and interface usability constitute a substantive HCI study.
- "Benchmarking Transformer Inference Across GPU and FPGA Accelerators"
  -> relevant / 3. Computer architecture and ML-system performance are directly evaluated.
- "A General Graph Neural Network Architecture Evaluated on Molecules and Citation Networks"
  -> relevant / 2. The general learning architecture is the main contribution; application
  datasets are evaluation settings rather than the research objective.
- "Detecting Water-Main Failures with a New Streaming Anomaly-Detection Framework"
  -> relevant / 2. The streaming method is substantively designed and evaluated, while the
  infrastructure application shares the focus.
- "Deep Neural Network for Automated Tumor Segmentation in MRI"
  -> maybe / 1. A real computer-vision method is developed, but the primary objective and
  claims concern a medical-imaging task in an excluded application domain.
- "Predicting Protein-Ligand Binding with a Modified Transformer"
  -> maybe / 1. The modified model is a substantive computational element, but drug discovery
  and biochemical performance remain the primary focus.
- "Random Forest Mapping of Drought Severity from Satellite Imagery"
  -> irrelevant / 0. A standard ML method is used to produce a climate/remote-sensing result;
  no algorithmic or computer-system contribution is shown.
- "Molecular Dynamics Simulation of Polymer Crystallization"
  -> irrelevant / 0. Computation is a tool for a materials-science question, not the subject.
- "Social Media Use and Adolescent Well-Being"
  -> irrelevant / 0. The online platform is a data source and social setting; no HCI or
  computing artifact is substantively studied.
- "Finite-Element Analysis of Seismic Loads on Concrete Bridges"
  -> irrelevant / 0. Standard computational analysis supports a structural-engineering study.
- "Effects of Cache Replacement Policies on Database Query Latency"
  -> relevant / 3. Cache algorithms and database-system performance are the central subject.
