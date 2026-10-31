"""Second-pass mechanism audit. Retire only new proposals, preserving all original 103 links."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[2];folder=root/'research/connection-review/batches'
edges=[e for p in sorted(folder.glob('0[1-8]-*.json')) for e in json.loads(p.read_text())['edges']]
remove={
('CPE-09','MLC-07'):'The cryogenic stack specifies no learning-workload mapping, so a device-efficiency aspiration is not a concrete route to the brain-comparable system budget.',
('CHM-01','PHA-05'):'Generic selective synthesis is not a specified intracellular activation-cascade mechanism. This was an overly broad chemical-fabrication relevance link.',
('CRX-07','BCH-03'):'A static single-molecule structure does not specify an in-vivo folding, chaperone or aggregation mechanism; retain this as a possible research relevance, not a directed capability arrow.',
('GEN-05','GEN-10'):'Examples of orphan-gene function alone do not specify a quantitative robustness/evolvability mechanism. The proposed model-input direction was too generic.',
('NEU-10','MLC-10'):'The source provides no rule-to-algorithm translation. Generic biological intelligence laws were being used as an underspecified architecture input.',
('NEU-04','ANS-07'):'The source is adult brain/plasticity regulation; the proposal supplied no qualified peripheral-nerve bridge. A caveat alone did not justify the tissue transfer.',
('MIC-10','EMR-02'):'A general metabolite/receptor map supplies no specific septic-shock control mechanism. Target discovery relevance was overstated as a capability connection.',
('BCH-06','EMR-05'):'An ATP-coupling account does not provide a protective suppression actuator or state trajectory. Knowledge of energy production alone did not justify this clinical route.',
('IND-07','SWE-10'):'A broad knowledge-work productivity account does not specify a software-agent implementation or reliable operational evaluation; the proposed benefit was generic.',
('IND-09','CHE-06'):'Generic socio-technical error-proofing lacks a chemical-plant hazard/control mapping. Chemical safety and control routes are already represented by more specific entries.',
('BCH-07','BIF-08'):'Post-translational modifications and the target’s epigenetic/post-transcriptional code are distinct. No explicit coupling mechanism was supplied in the two descriptions.',
('CHM-07','CHM-01'):'An externally steered reaction does not specify a homogeneous catalyst’s intrinsic selective mechanism; the proposed combined experiment added an unreviewed bridge.'
}
retired=[]
for pair,reason in remove.items():
 matches=[e for e in edges if (e['fromId'],e['toId'])==pair];assert len(matches)==1,pair
 retired.append(dict(id=matches[0]['id'],expectedPayload=matches[0],reason=reason))
unresolved={
'CPE-09':{'category':'insufficient-system-bridge','reason':remove[('CPE-09','MLC-07')]},
'CHM-01':{'category':'insufficient-intervention-mechanism','reason':'No specific downstream synthetic target or catalyst-construction input is specified; generic fabrication and external-field relevance links were retired.'},
'CHM-07':{'category':'insufficient-intervention-mechanism','reason':remove[('CHM-07','CHM-01')]},
'CRX-07':{'category':'insufficient-state-bridge','reason':remove[('CRX-07','BCH-03')]},
'GEN-05':{'category':'insufficient-model-bridge','reason':remove[('GEN-05','GEN-10')]},
'NEU-10':{'category':'insufficient-model-bridge','reason':remove[('NEU-10','MLC-10')]},
'ANS-07':{'category':'unqualified-tissue-transfer','reason':remove[('NEU-04','ANS-07')]},
'EMR-02':{'category':'missing-clinical-mechanism','reason':remove[('MIC-10','EMR-02')]},
'EMR-05':{'category':'missing-clinical-mechanism','reason':remove[('BCH-06','EMR-05')]},
'IND-07':{'category':'insufficient-operational-bridge','reason':remove[('IND-07','SWE-10')]},
'BCH-07':{'category':'scope-mismatch','reason':remove[('BCH-07','BIF-08')]}
}
record=dict(id='09-reviewed',fields=[],reviewedIds=[],edges=[],unresolved=unresolved,branches=[],retiredEdges=retired,rejectedCandidates=[dict(fromId=a,toId=b,reason=r) for (a,b),r in remove.items()])
(folder/'09-reviewed.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print('Retired',len(retired),'new proposals after substantive review; original links unchanged.')
