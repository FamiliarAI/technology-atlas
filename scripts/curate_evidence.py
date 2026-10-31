"""Reviewed paraphrases of scoped findings. No dates of future achievement or inferred dependencies."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
OLD=json.loads((ROOT/'research/prototype-before-source-correction/curated.json').read_text())
lookup={s['id']:s for s in OLD['sources']}
results=[]
def result(id,source,domain,title,kind,claim,scope,limits,url,published,date_label,locator,review,version=None,correction=None):
 old=lookup[source]
 results.append(dict(id=id,domain=domain,title=title,kind=kind,status='reported-result',claim=claim,scope=scope,limitations=limits,source=dict(id=source,title=old['title'],url=url,published=published,dateLabel=date_label,version=version,locator=locator,checkedAt='2026-10-30',checkMethod=review,accessNote='Destination and cited passage opened during review; access can change.',correction=correction)))
result('EV-CLIP','clip','AI','Zero-shot visual transfer with CLIP','Benchmark study',
 'The authors report image classification transfer without task-specific training, including matching the original ResNet-50 on ImageNet.',
 'Evaluations across more than 30 vision datasets after image–text pretraining.',
 'This supports transfer on the evaluated datasets. It does not establish general visual understanding or an autonomous scientist.',
 'https://arxiv.org/abs/2103.00020v1','2021-02-26','First preprint submission','Abstract, paragraphs 2–3',
 'Primary preprint abstract and submission record read; summary restricted to the reported benchmarks.','arXiv v1')
result('EV-GNS','gns','AI','Learned particle-based simulation','Simulation study',
 'The authors report a graph-network simulator that transfers to different initial conditions, longer rollouts and larger particle systems in the evaluated physical simulations.',
 'Particle-based simulations involving fluids, rigid solids and deformable materials.',
 'The evidence concerns evaluated simulated systems. It does not establish a universal physical model, reliable real-world causal reasoning or experimental planning.',
 'https://arxiv.org/abs/2002.09405v2','2020-02-21','First preprint submission','Abstract, paragraphs 1–2',
 'Primary preprint abstract and version history read; scope restricted to the evaluated simulations.','arXiv v2 · revised 2020-09-14')
result('EV-AF','af','AI','Protein structure prediction in CASP14','Benchmark study',
 'AlphaFold achieved protein-structure prediction accuracy competitive with experimental structures in a majority of CASP14 cases, according to the paper.',
 'Blind protein-structure assessment; the paper also evaluates recently deposited protein structures.',
 'The paper describes lower accuracy with shallow sequence alignments and difficulties with some proteins shaped by other chains. This does not demonstrate biological function or drug efficacy.',
 'https://www.nature.com/articles/s41586-021-03819-2?error=cookies_not_supported','2021-07-15','Published online','Abstract; CASP14 assessment; MSA depth and cross-chain contacts',
 'Primary publisher article read at the cited sections; date cross-checked against its PubMed record.')
result('EV-RT2','rt2','Robotics','RT-2 control on evaluated robot tasks','Robot experiments',
 'The authors report improved generalization to novel objects and interpretation of some commands absent from robot training data, using vision-language-action models.',
 'RT-2 policies evaluated over approximately 6,000 trials in the reported robotic settings.',
 'The reported tasks do not establish universal manipulation, dependable deployment across arbitrary environments, or a safety guarantee.',
 'https://arxiv.org/abs/2307.15818v1','2023-07-28','First preprint submission','Abstract, evaluation and example capabilities',
 'Primary preprint abstract and submission record read; claims restricted to the reported evaluations.','arXiv v1')
result('EV-DIFF','diff','Robotics','Diffusion-based manipulation policies','Robot benchmarks',
 'The authors report better average task performance than the compared robot-learning baselines across 12 tasks from four manipulation benchmarks.',
 'Visuomotor control using an action-denoising policy; selected manipulation benchmarks.',
 'Relative benchmark performance is not a guarantee for new tasks, embodiments or deployment conditions. It does not establish universal dexterity.',
 'https://arxiv.org/abs/2303.04137v5','2023-03-07','First preprint submission','Abstract, benchmark description',
 'Primary preprint abstract and version history read; summary follows the linked extended version.','arXiv v5 · revised 2024-03-14')
result('EV-GNOME','gnome','Materials','Computed candidate crystal structures','Computational study',
 'GNoME identified candidate crystal structures with predicted stability under the paper’s computational comparisons. The authors also report matches to independently realized structures.',
 'Graph-network exploration with first-principles calculations and comparisons to materials databases.',
 'Predicted stability is not synthesis or useful product performance. The paper identifies synthesizability, competing phases and dynamic stability as remaining problems.',
 'https://www.nature.com/articles/s41586-023-06735-9?error=cookies_not_supported','2023-11-29','Published online','Abstract; validation through experimental matching; conclusion',
 'Primary publisher abstract, validation discussion and conclusion read; date and abstract cross-checked in PubMed.')
result('EV-OSK','osk','Longevity','Visual-function effects in mice','Animal experiments',
 'The authors report that OSK expression in mouse retinal ganglion cells promoted axon regeneration and improved visual function in the studied glaucoma and aging models.',
 'Mouse retinal experiments involving Oct4, Sox2 and Klf4 expression.',
 'These animal retinal results do not establish a human treatment, systemic rejuvenation, extended human healthspan or long-term human safety.',
 'https://www.nature.com/articles/s41586-020-2975-4?error=cookies_not_supported','2020-12-02','Published online','Abstract; retinal regeneration and visual-function experiments',
 'Primary publisher abstract and corresponding primary manuscript in PMC read; result narrowed to mice and retinal function.')
result('EV-PACE','pace','Longevity','A methylation-based aging measure','Observational study',
 'The authors developed DunedinPACE from longitudinal physiological measurements and evaluated the methylation-based measure in additional datasets.',
 'Training from a New Zealand birth cohort; follow-up evaluations in other human datasets.',
 'The paper notes limited population diversity. Validating a treatment surrogate still requires evidence that intervention-driven score changes track healthy-lifespan outcomes.',
 'https://elifesciences.org/articles/73420','2022-01-14','Accepted manuscript first published','Abstract; Discussion, limitations and surrogate-endpoint paragraph',
 'Primary publisher abstract, discussion and version dates read.','Version of record · 2022-02-17')
result('EV-CALERIE','calerie','Longevity','A biomarker change in CALERIE','Trial biomarker analysis',
 'A post hoc analysis of CALERIE reports a small intervention effect on DunedinPACE, with no significant changes in PhenoAge or GrimAge estimates.',
 'Blood methylation analysis from a two-year randomized calorie-restriction trial in adults without obesity.',
 'This is a biomarker result, not demonstrated longer human lifespan. The authors say long-term disease and mortality follow-up is needed.',
 'https://www.nature.com/articles/s43587-022-00357-y?error=cookies_not_supported','2023-02-09','Published online','Abstract; author correction',
 'Current primary publisher abstract and linked correction read; date and summary cross-checked in PubMed.',correction=dict(title='Author correction',url='https://www.nature.com/articles/s43587-023-00432-y?error=cookies_not_supported',published='2023-05-09',note='Corrects an author affiliation; the correction does not report a change to the study result.'))
audit=dict(version='evidence-2026-10-30-v1',checkedAt='2026-10-30',before=dict(cards=24,observedLabels=5,partialLabels=6,forecastLabels=13,forecastWindows=19,successCriteria=24,dependencyRoutes=16,arrows=29,sources=11),after=dict(results=len(results),fields=4,forecastWindows=0,dependencyRoutes=0,arrows=0,sources=len(results)),policy='Primary-source scope review, not independent replication or absolute proof. No inferred causal prerequisites are displayed.',changes=[
 'Removed all 19 invented future windows and all 24 invented success criteria from the website.',
 'Removed all 16 hypothetical prerequisite routes and all 29 dependency or accelerator arrows.',
 'Replaced broad milestone labels with nine scoped reported results. Three are computational or vision benchmarks, two concern robotic control, one concerns candidate materials and three concern aging research.',
 'Future aspirations, unsupported connections and the original prototype dataset are retained outside the served website.',
 'Old browser review data is preserved under its original storage key, but cannot become evidence in this view.'
],excluded=[dict(id='alab',title=lookup['alab']['title'],reason='Omitted from the evidence view. The 2026 correction changes novelty wording and reported compound-identification outcomes; a new scoped claim has not been curated.',sourceUrl='https://www.nature.com/articles/s41586-025-09992-y?error=cookies_not_supported',checkedAt='2026-10-30'),dict(id='battery',title=lookup['battery']['title'],reason='Omitted. The primary abstract was not accessible through the checked routes in this review; related search snippets do not suffice for a displayed experimental claim.',sourceUrl='https://www.nature.com/articles/s41560-023-01231-w',checkedAt='2026-10-30')])
out=dict(schemaVersion=2,version=audit['version'],checkedAt='2026-10-30',domains=['AI','Robotics','Materials','Longevity'],results=results,edges=[],audit=audit)
(ROOT/'web/data/evidence.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
print(f'{len(results)} scoped results; no forecast dates, invented success criteria or dependency edges.')
