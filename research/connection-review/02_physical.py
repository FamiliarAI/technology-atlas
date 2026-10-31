from scripts.curate_remaining import Batch
b=Batch('02-physical',['Physics','Astronomy','Optical Engineering','Electrical Engineering','Thermodynamics','Rheology','Crystallography','Chemistry']);a=b.a;u=b.u
# Model/measurement feedback is explicitly distinct from prerequisite ordering.
a('PHY-05','THR-09','A proposed information-preservation mechanism could supply a consistency condition when constructing the horizon-thermodynamics framework.','Solving an information question does not by itself unify gravitational and laboratory thermodynamics.','enabling')
a('THR-09','PHY-05','A proposed thermodynamic framework could supply checks against which to test candidate information-preservation accounts.','This is iterative consistency feedback, not an experimentally established resolution or a required sequence.','feedback')
a('PHY-03','AST-07','A candidate dark-energy mechanism could motivate an expansion model to compare with the proposed Hubble-tension resolution.','The tension might instead involve calibration or other physics; a dark-energy explanation is not assumed.','alternative-route',group='hubble-interpretation')
a('AST-07','PHY-03','A consistent expansion-rate result could constrain a candidate dark-energy explanation.','An expansion constraint would not identify a microscopic cause; this is proposed observation-to-model feedback.','feedback')
a('AST-04','AST-10','Characterizing an earliest-star population could help compare stellar-seed interpretations with other proposed early-black-hole origins.','Detecting stars does not establish which black-hole growth channel occurred; both timing and population inference remain uncertain.')
a('OPT-02','HCI-02','A flat achromatic focusing element could be tested as part of a compact visible-light AR optical path.','Focusing is not image generation, wearability, zero latency or a contact-lens implementation.','enabling')
a('OPT-07','HCI-08','A parallax-correct volumetric display could be a visual channel for a proposed remote shared environment.','A display does not establish physical co-location, interaction fidelity or all other sensory channels.','enabling')
a('OPT-04','CPE-05','Cascadable optical switches could provide logic components in a proposed photonic-electronic computing architecture.','Gain and cascaded logic do not establish memory, integration, lossless conversion or general computing performance.','enabling')
a('OPT-03','QUA-04','A photon-mediated network proposal could test deterministic emitters as a node or link subsystem.','An on-demand photon source is not an entanglement-distribution protocol, a repeater or a global network.','enabling')
a('OPT-06','QUA-04','A fiber-based network route could investigate whether lower attenuation reduces the loss budget for transmitted states.','Fiber loss alone does not establish repeaters, fidelity or useful distribution rates.')
a('OPT-09','HCI-02','Recovering optical quality after damage could be investigated for durability of a wearable optical overlay.','Self-repair would not solve image generation or the original perfect-overlay claims; suitability for an eye-worn device is unreviewed.')
a('OPT-04','OPT-10','Cascadable optical devices could provide a signal-control component for a proposed multi-stage optical accelerator.','No particular neural operation, energy advantage or scalable integration follows from the switch alone.','enabling')
a('OPT-10','MLC-07','An optical matrix-operation accelerator could be another hardware approach to investigate learning-system energy use.','The source’s exascale-per-watt claim is not validated, and accelerator power is not total system power.','alternative-route',group='efficient-learning-hardware')
a('QUA-02','ELE-03','An ambient coherent-qubit implementation could be investigated as a physical ingredient in a proposed room-temperature computing platform.','The source platform need not be topological; compatibility with protected gates remains unresolved.','enabling')
a('QUA-06','ELE-03','Protected-gate and correction methods could be investigated for a proposed ambient topological platform.','Performance cannot be transferred to ambient conditions by assumption.','enabling')
a('ELE-07','BME-08','A suitable energy-harvesting device could supply a candidate power subsystem for an implantable sensor network.','Ambient environmental performance does not establish in-body power, safety, infection resistance or universal sensor coverage.','enabling')
a('THR-01','THR-02','Consistent state and entropy accounting could help state a proposed nonequilibrium precision-cost bound.','A definition does not prove a universal bound, and a universal framework may not be necessary for restricted systems.','enabling')
a('THR-03','THR-02','Strong-coupling quantum work/heat relations could be used to test the quantum domain of a candidate precision-cost relation.','A fluctuation theorem does not automatically imply the desired tight bound.')
a('THR-01','THR-04','Nonequilibrium accounting could supply state and dissipation quantities for a proposed active-matter description.','State variables alone do not derive motility, phase separation or collective dynamics.','enabling')
a('THR-04','RHE-06','An active-matter energy description could contribute bookkeeping for a proposed stress-and-flow model of active systems.','Thermodynamic potentials do not alone determine viscosity or full constitutive dynamics.','enabling')
a('THR-07','BCH-10','Reaction-network flux and dissipation models could help evaluate candidate self-sustaining biochemical networks.','Thermodynamic feasibility does not establish heredity, replication or Darwinian evolution.','enabling')
a('THR-07','CHM-06','A network-level accounting model could constrain energy and flux in candidate self-copying chemical experiments.','Network dynamics do not establish mutation, selection or open-ended evolution.','enabling')
a('THR-06','CHE-05','Finite-power efficiency bounds could be benchmarks when evaluating a proposed plant heat-integration scheme.','A bound can limit the source’s perfect-closure aspiration rather than enable it; no zero-loss design is asserted.')
a('THR-08','RHE-07','A framework for metastability and broken ergodicity could help formulate candidate material-history states.','It does not by itself determine transient flow laws, aging times or memory in all fluids.')
a('RHE-01','CHE-03','Constitutive flow relations could be input models for a proposed multiphase process scale-up theory.','A material relation does not settle transport, reaction kinetics or every scale-up effect.','enabling')
a('RHE-02','RHE-04','Instability criteria could help design experiments intended to avoid shear bands and secondary-flow artifacts.','No criterion is assumed universally sufficient or experimentally artifact-free.','enabling')
a('RHE-03','RHE-01','Topology-dependent polymer response could supply a restricted class of constitutive behavior for a broader model.','A ring/branched-polymer theory would not establish a universal law across all complex fluids.')
a('RHE-04','RHE-01','Better-controlled measurements could provide reference tests of a candidate constitutive equation.','An artifact-reduction protocol is not proof of a universally valid equation.')
a('RHE-01','RHE-04','Candidate flow predictions could help identify conditions where a measurement protocol is likely to be nonuniform.','This is model-to-experiment feedback; the model and artifact-free measurement do not prove one another.','feedback')
a('RHE-05','CHE-03','Non-local flow and confinement models could inform transport terms in a proposed scale-up model.','A confined-flow theory does not resolve every multiphase or chemical scale-up problem.','enabling')
a('RHE-07','RHE-01','A material-history state law could supply a memory term within a broader constitutive model.','Covering aging and thixotropy does not establish other material classes.','enabling')
a('RHE-08','RHE-01','An extensional-response closure could supply one deformation mode in a proposed general constitutive model.','Extension alone does not determine every shear, normal-stress or structural response.','enabling')
a('RHE-09','RHE-01','A shape- and friction-sensitive granular relation could provide a candidate granular-material component.','A granular closure would not establish a universal fluid law.','enabling')
a('RHE-10','RHE-05','Molecular/slip observations could inform boundary conditions in the ultra-confined limit of a non-local model.','A quantum-to-continuum link need not apply to larger-scale confined flows.')
a('CRX-01','CRX-04','Preparing suitable crystals could supply samples for a proposed time-resolved crystallographic experiment.','Universal crystallization is not required for every experiment, and crystallization may change the state of interest.','enabling')
a('CRX-04','BCH-01','Time-dependent structural observations could help test candidate catalytic mechanisms.','A structural movie does not measure all energetic barriers or establish a universal catalysis theory.')
a('CRX-03','BIF-06','Conformational ensembles could provide candidate structures when testing interaction models involving flexible regions.','An ensemble does not determine affinities, all interfaces or all cellular contexts.','enabling')
a('CRX-07','BCH-03','Single-molecule structures could provide additional constraints for a candidate folding model.','A structure is not an in-vivo folding pathway or its chaperone and aggregation dynamics.')
a('CRX-08','CRX-04','Recovering phases could contribute to reconstructing structures from proposed time-resolved diffraction data.','Phase recovery does not provide temporal resolution, good samples or a complete reaction mechanism.','enabling')
a('CHM-01','PHA-05','Selective functionalization could provide a synthetic step for testing variants of a proposed prodrug activation design.','A synthesis method does not establish disease-specific activation or safe drug behavior.')
a('CHM-07','CHM-01','External pathway control could be tested as a way to bias channels in candidate bond-functionalization experiments.','This is not a universal field-control solution or a guarantee of perfect catalyst selectivity.')
a('CHM-08','CHM-02','A proposed molecular assembler could provide a fabrication route for selected designed catalyst candidates.','Precise assembly alone does not establish enzyme folding, specificity or catalytic performance.')
for id,reason in {
'PHY-01':'No specified quantum-gravity construction or experimental consequence connects this broad theoretical resolution to a concrete capability in the collection.',
'PHY-02':'Particle identification alone does not specify a manipulable device or downstream method. No usable interaction mechanism can be inferred from the target statement.',
'PHY-04':'Observing decay is evidence about fundamental physics, not a specified enabling technology; the source supplies no downstream construction.',
'PHY-06':'The target leaves the hierarchy solution open. Different outcomes would not imply the same engineering route, so no conditional invention is treated as a dependency.',
'PHY-07':'A primordial polarization observation does not directly establish one of the listed engineering capabilities; a particular downstream inference was not specified.',
'PHY-08':'The identity of early-universe processes is a discovery goal without a defined experimental or engineering use among the other source entries.',
'PHY-09':'Its cosmological initial-state question overlaps, but is not the same as, THR-05’s no-initial-condition derivation. Shared wording does not justify a causal arrow.',
'PHY-10':'No monopole interaction or controllable implementation is specified, so a route to magnets, energy or computing would invent physical properties.',
'AST-01':'No listed optical target specifies the sensitivity, survey strategy and orbit confirmation needed for this particular search; a generic telescope-improvement arrow was rejected.',
'AST-02':'Confirming life requires source-specific atmospheric interpretation and exclusion of alternatives. None of the reviewed milestones supplies that specific inference chain.',
'AST-03':'The source asks for a solar-heating mechanism but no listed engineering target provides a defined application route beyond generic plasma relevance.',
'AST-05':'No relic-neutrino detection mechanism or specific resulting capability is supplied by the collection; generic detector claims would be invented.',
'AST-06':'A burst-origin explanation does not itself provide a calibrated propagation or matter-mapping method; a link to the baryon census needs a more specific measurement model.',
'AST-08':'A confirmed artificial signal is an observational goal, not a specified technology dependency. No justified signal-generation or detection route is defined here.',
'AST-09':'The collection does not specify a quantitative matter-tracing method whose required inputs match another milestone. Related cosmology goals alone do not justify an arrow.',
'OPT-01':'The visible-cloak target overlaps MAS-05/ELE-04 rather than supplying a separate component. Feasibility constraints require review before treating any perfect cloak as an input.',
'OPT-05':'A generic correction instrument could aid many observations, but no target here specifies a wavefront-limited measurement where this full universal capability is needed or causally scoped.',
'OPT-08':'The simultaneous passive, linear and reciprocal-breaking constraints require feasibility review. No concrete implementation route is supplied; it is not assumed usable as a component.',
'ELE-01':'This is the canonical target of source duplicate flags MAS-01 and CRM-05. The source equivalence is preserved without a duplicate-to-canonical causal arrow.',
'ELE-02':'Its wireless-transfer goal overlaps PWR-07. No separate component mechanism makes one complete transfer ambition a prerequisite for the other.',
'ELE-04':'The broadband cloak/lens ambition subsumes overlapping optical and material targets; scope overlap is not a causal mechanism.',
'ELE-05':'This switch target overlaps CPE-01’s device ambition. A causal arrow between near-equivalent switches would manufacture coverage.',
'ELE-06':'The interface scope overlaps BME-02/HCI-01 and allows different invasive/non-invasive implementations. No separate component mechanism was established for a directional arrow.',
'ELE-08':'This integrated processor ambition overlaps CPE-05; no independent subsystem relationship between the two complete platforms is justified.',
'ELE-09':'The autonomous-grid architecture overlaps PWR-05/PWR-10; a complete architecture should not be treated as another complete architecture’s prerequisite.',
'ELE-10':'No listed component specifically supplies the stated non-line-of-sight terahertz propagation, transceiver and rate requirements; generic optical switching does not solve them.',
'THR-05':'A derivation excluding special initial conditions is not supplied by PHY-09’s initial-state explanation. These are distinct foundational questions, not a sequence.',
'THR-10':'A stable negative-temperature state for the stipulated spectrum needs its own feasibility and ensemble model. No engine or storage benefit is inferred from the temperature label.',
'CHM-04':'A methane-conversion catalyst does not by itself deliver a listed petroleum production or circularity system. A specific process integration and feedstock route needs review.',
'CHM-05':'This molecular artificial-photosynthesis ambition overlaps MAS-09’s system/catalyst scope. No route is claimed to establish the other goal or a storage-efficiency target.'
}.items():u(id,reason,'source-equivalence' if id=='ELE-01' else 'unresolved-mechanism')
b.reject('PHY-07','AST-10','An inflation observation does not directly determine the growth history of particular early black holes.')
b.reject('ELE-02','PWR-07','Overlapping wireless-transfer goals are not a causal chain.')
b.reject('THR-10','PWR-04','A temperature sign is not a demonstrated storage or efficiency mechanism.')
b.branch('active-fluid-models','Active matter and flow measurements',['THR-01','THR-04','RHE-06','RHE-02','RHE-04','RHE-01','RHE-03','RHE-07','RHE-08','RHE-09'])
b.branch('quantum-optical-links','Optical links and quantum networks',['OPT-03','OPT-06','QUA-09','QUA-04','OPT-04','CPE-05','OPT-10','MLC-07'])
b.branch('early-universe-models','Cosmological models and observations',['AST-04','AST-10','PHY-03','AST-07','PHY-05','THR-09'])
b.save()
