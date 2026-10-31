from scripts.curate_remaining import Batch
b=Batch('04-earth-transport',['Aerospace','Rocketry','Marine and Naval Engineering','Petroleum Engineering','Geology','Oceanography']);a=b.a;u=b.u
# Vehicle applications state their operating-range and subsystem assumptions explicitly.
a('CRM-06','AER-05','An oxidation-resistant high-temperature ceramic could be investigated as a turbine material candidate.','Its temperature exposure does not establish rotating-load strength, processing, lifetime or a cooling-free turbine.','enabling')
a('CRM-06','AER-10','A qualified hot-oxidation ceramic could provide a protective constituent of a proposed thermal-protection layer.','Oxidation resistance alone does not establish ablation repair, emissivity control or repeated-flight integrity.','enabling')
a('CRM-02','AER-10','A high-temperature crack-repair process could be investigated as one repair mechanism in an adaptive heat shield.','A load-bearing ceramic repair result would not establish a complete re-entry protection system.','enabling')
a('CRM-02','ROC-05','Autonomous repair could be tested as one way to reduce maintenance in a reusable protection material.','Repair is not proof of zero degradation or 100-plus refurbishment-free re-entries.')
a('AER-06','AER-01','A qualified high-speed flow-control method could be tested in the intake or combustion-flow portion of an engine architecture.','Control authority and power demands do not establish stable combustion or net-positive thrust for hours.','enabling')
a('AER-06','AER-02','Active flow control could be investigated as one approach to shaping a vehicle’s shock signature.','The source does not establish disappearance of ground-level sonic boom or efficient cruise.','alternative-route',group='boom-research')
a('AER-07','AER-02','Controlled geometry changes could be another way to investigate a specified shock-signature design.','Wing morphing does not establish full-vehicle boom elimination; approaches may combine.','alternative-route',group='boom-research')
a('MEC-03','AER-07','Motion synthesis could help design candidate mechanisms for a specified wing-shape change.','Seamless skins, aerodynamic loads, low mass and zero complexity penalty remain separate.','enabling')
a('CRM-10','AER-07','A compatible reversible-strain material could provide an actuation candidate for wing morphing.','The source’s ceramic temperatures and strains must match the flight design; no compatibility is assumed.','enabling')
a('AER-01','ROC-04','A qualified air-breathing engine could supply a candidate high-speed mode within a combined-cycle design.','The source does not supply low-speed takeoff, transition to rocket mode or orbital insertion.','enabling')
a('ROC-04','AER-03','A combined-cycle engine could be investigated as a runway-launch route within an SSTO design.','An engine does not satisfy total vehicle mass, ascent, return or airline-like turnaround.','enabling')
a('ROC-05','AER-03','A reusable protection material could address one refurbishment burden in a reusable orbital vehicle.','Thermal-protection lifetime does not establish propulsion, structural life or rapid vehicle turnaround.','enabling')
a('MAS-03','AER-08','A candidate solid-electrolyte cell could be evaluated within a battery-based aircraft power route.','An electrolyte does not establish full-system specific energy, megawatt performance or thermal safety.','enabling')
a('NUC-01','ROC-02','A qualified irradiation-resistant structural material could reduce one lifetime constraint in a nuclear thermal engine.','It does not establish hydrogen compatibility, restart, thrust or the specific-impulse target.')
a('NUC-04','ROC-02','A passive-safety core concept could contribute to evaluating a flight reactor’s safety argument.','Ground-style walk-away safety does not establish flight qualification, mass or propulsive performance.')
a('CRX-09','ROC-03','Operando extreme-condition measurements could help investigate candidate hydrogen phases and their stability changes.','A measurement tool does not establish metallic hydrogen, metastability at storage conditions or a usable propellant.')
a('PWR-07','ROC-08','A qualified microwave energy-transfer system could supply a candidate power-delivery channel for beamed propulsion.','Transmitting power does not establish vehicle coupling, pointing through ascent, thrust or orbital insertion.','enabling')
a('CHE-06','ROC-09','Autonomous process-control concepts could be adapted and tested for a specified extraterrestrial propellant plant.','Regolith/atmospheric chemistry, environmental qualification and production rate are not supplied by generic automation.','enabling')
a('ROB-01','ROC-09','Qualified robotic handling could support the physical feedstock and maintenance operations of an ISRU plant.','Dexterity does not supply extraction chemistry, power or the required production scale.')
a('RHE-01','ROC-10','A gel-handling design could use a constitutive model to investigate storage, pumping and injection behavior.','Flow prediction does not establish ignition safety, energy density or the proposed propulsion performance.','enabling')
a('MNE-07','MNE-01','Controllable hull roughness or shape could be tested as a way to maintain a selected air-layer configuration.','There is no asserted stable layer for every speed or sea condition.','enabling')
a('MEC-07','MNE-02','A water-propulsor implementation could supply a candidate architecture for investigating the marine target.','The biomimetic aspiration does not establish no cavitation, noise or loss at every speed and depth.','enabling')
a('MAS-08','MNE-03','A candidate repellent surface could be screened under specified marine-fouling conditions.','Self-cleaning is not equivalent to non-toxic prevention of all organism attachment for decades.')
a('MET-06','MNE-04','A candidate corrosion-resistant alloy could be investigated for a selected marine structural use.','Microbial, sediment and splash-zone exposures require separate tests; no zero corrosion rate is established.','enabling')
a('ELE-01','MNE-06','A qualified high-current superconductor could supply a magnet component in a proposed superconducting propulsion route.','A conductor does not supply the complete fluid-force, energy-conversion and ship-integration design.','enabling')
a('MEC-05','MNE-07','Reconfigurable load-bearing mechanisms could provide candidate adaptive hull elements.','Hydrodynamic loads, seals, response control and reversibility in seawater remain unresolved.','enabling')
a('MAS-06','MNE-09','A qualified thermoelectric subsystem could be investigated for the thermal-gradient branch of onboard energy harvesting.','A gradient must provide usable external energy; seawater is not assumed a net energy source, and propulsion demand may exceed harvest.','enabling')
a('MEC-05','MNE-10','Damage diagnosis, load redirection and repair concepts could provide a starting architecture for naval adaptation.','A general mechanical system does not establish continued operation after extreme naval damage.','enabling')
a('RHE-05','PET-01','A porous-flow model could help compare candidate displacement strategies in a defined reservoir.','A flow model does not establish a universal recovery chemistry or the source’s recovery fraction.','enabling')
a('PET-02','PET-05','Measured subsurface fluid and pressure states could be input data for testing a reservoir simulator.','Measurement resolution and model uncertainty remain limited; the stated forecasting error is not established.','enabling')
a('PET-05','PET-01','A qualified simulator could help select and evaluate a proposed displacement program.','A production forecast does not create the universal recovery mechanism.')
a('PET-02','PET-08','Updated subsurface state information could help a drilling controller evaluate some fluid or trajectory conditions.','It cannot exclude all mechanical or geological dysfunction or establish zero downtime.','enabling')
a('ROB-09','PET-08','Controller verification could help test specified motion and decision constraints in an automated drilling design.','Proofs depend on models and do not remove unknown geological conditions or hardware failure.')
a('PET-02','PET-09','Subsurface state observations could supply part of a monitoring argument for an injection design.','Monitoring cannot by itself guarantee indefinite retention or the proposed recovery bonus.','enabling')
a('CHE-08','PET-04','A combined reaction/separation process could be investigated as one module in a defined produced-water treatment train.','No specific contaminant coverage, recovery rate or zero-discharge process is established.','enabling')
a('CHM-04','PET-07','For a methane-containing feed, a conversion catalyst could be tested as one route to a liquid product.','Selectivity is not total energy efficiency, and reservoir conditions, catalysts and feeds need qualification.','enabling')
a('GEO-03','GEO-06','A proposed deep-mantle dynamical model could supply a forcing hypothesis to test in a continental-cycle model.','The origin of deep structures does not establish exact drivers or periodicity of continent assembly.')
a('GEO-02','GEO-06','An account of plate-tectonic initiation could supply initial-condition hypotheses for a long-term tectonic model.','An initiation mechanism does not by itself explain later cycles or guarantee regular periods.')
a('GEO-08','CIV-10','A qualified sediment/erosion law could contribute an exposure model for specified coastal infrastructure.','It would not establish affordable protection against all hazards or all time horizons.','enabling')
a('GEO-04','CIV-10','A qualified precursor forecast could inform a defined preparedness or hazard-evaluation policy.','A forecast is not a material defense or a universal earthquake prediction guarantee.')
a('OCE-09','OCE-01','An internal-wave cascade model could help estimate one specified contribution to the deep-ocean mixing budget.','It does not establish the complete budget or the importance of other sources.','enabling')
a('OCE-01','OCE-07','A qualified mixing closure could be an input to investigating candidate overturning-circulation states.','A mixing budget does not establish exact stability thresholds or deterministic future circulation.','enabling')
a('OCE-04','MNE-07','A qualified extreme-wave model could help compare a hull-control response with a specified sea-state scenario.','A wave mechanism does not establish timely prediction or a hull able to respond safely.')
a('OCE-05','OCE-10','Coastal groundwater-flux estimates could provide one boundary input to a proposed ocean-chemistry budget.','A coastal flux estimate does not determine the entire ocean’s buffering capacity or resilience threshold.','enabling')
for id,reason in {
'AER-04':'No reviewed source specifies a full-scale transition-control mechanism for maintaining laminar flow. Generic flow-separation control does not establish this distinct requirement.',
'AER-09':'No qualified inertial or quantum sensing, calibration and drift-correction architecture is specified by another original milestone.',
'ROC-01':'This orbital vehicle ambition overlaps AER-03 nearly verbatim. Retain both as overlapping goals rather than invent a vehicle-to-vehicle prerequisite.',
'ROC-06':'No reviewed source supplies a suitably lightweight multi-megawatt power, conversion and heat-rejection design; nuclear-power ambitions do not automatically meet in-space mass and thrust needs.',
'ROC-07':'No specified shielding/refrigeration architecture supplies the multi-year propellant heat balance. A cryogenic computing package is not a storage solution.',
'MNE-05':'Fiber transmission and terrestrial terahertz communication do not solve repeater-free underwater wireless propagation. No qualified underwater link mechanism was identified.',
'MNE-08':'No reviewed hull/restoring-force and sea-state mechanism establishes the stated stability. A vibration isolator would not automatically stabilize the entire vessel.',
'PET-03':'No reviewed source specifies an injectable reservoir-qualified catalyst for the required heavy-hydrocarbon cracking; methane oxidation is a different reaction goal.',
'PET-06':'Net-zero operation needs an explicit energy/emissions system boundary and balance. Water reuse or gas conversion alone does not establish a net-zero platform.',
'PET-10':'No listed material or system is qualified for the simultaneous stated pressure, temperature, chemistry and production lifetime; a generic hot alloy is not enough.',
'GEO-01':'A historical impact reconstruction does not specify a direct capability or required input among the other original targets.',
'GEO-05':'No reviewed measurement or inversion model identifies core light elements; mantle and surface dynamics do not uniquely supply that composition.',
'GEO-07':'The missing-record explanation lacks a specified measurement or process pathway connecting it causally to another listed target.',
'GEO-09':'No particular emplacement mechanism is supplied, so no granite-to-geothermal or construction capability is inferred.',
'GEO-10':'The source leaves the polar-motion mechanism unspecified; related deep-Earth questions do not establish a directional dependency.',
'OCE-02':'No regional transfer model connects the proposed ENSO forecast to a specific agricultural or coastal-control capability. Generic weather-benefit arrows were rejected.',
'OCE-03':'The carbon-pump ambition has no reviewed quantitative coupling to another original target’s complete chemical or ecological endpoint.',
'OCE-06':'The bacterial glow mechanism is unspecified; a marine coordination observation is not assumed to provide a usable engineered microbial control system.',
'OCE-08':'The metabolic pathway is the discovery goal itself. No energy-harvesting or synthetic-metabolism implementation follows without identifying it.'
}.items():u(id,reason,'overlapping-target' if id=='ROC-01' else 'unresolved-mechanism')
b.reject('OPT-06','MNE-05','Guided fiber transmission is not repeater-free underwater wireless communication.')
b.reject('OCE-09','OCE-04','Internal-wave cascades and open-ocean surface rogue waves are not interchangeable mechanisms.')
b.reject('NUC-06','ROC-06','A gigawatt-hour lifetime energy target does not specify multi-megawatt instantaneous power or flight mass.')
b.reject('CHM-04','PET-03','Methane oxidation does not supply an injectable heavy-oil cracking catalyst.')
b.branch('reusable-flight','Reusable flight and thermal protection',['CRM-02','CRM-06','AER-10','ROC-05','AER-03','AER-06','AER-01','ROC-04'])
b.branch('marine-systems','Marine propulsion and adaptive hulls',['ELE-01','MNE-06','MEC-07','MNE-02','MEC-05','MNE-07','MNE-01','OCE-04'])
b.branch('reservoir-observation','Reservoir observation and operation',['PET-02','PET-05','PET-01','PET-08','PET-09','ROB-09','RHE-05'])
b.branch('ocean-coastal-models','Ocean and coastal model inputs',['OCE-09','OCE-01','OCE-07','OCE-05','OCE-10','GEO-08','GEO-04','CIV-10'])
b.save()
