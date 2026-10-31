from scripts.curate_remaining import Batch
b=Batch('08-quantitative',['Economics','Finance','Actuarial Science']);a=b.a;u=b.u
# These are model-input and evaluation proposals, not forecasts, advice or universal guarantee claims.
a('ECO-01','FIN-01','A qualified equity-premium explanation could supply one risk-premium component to test within a broader asset-pricing model.','A resolution of one puzzle does not explain every anomaly or forecast future returns.','enabling')
a('FIN-03','FIN-01','A qualified safe-rate explanation could constrain candidate discount-rate assumptions in a pricing model.','A historical explanation does not establish all risk premia or future rates.')
a('FIN-08','FIN-01','A limited-information equilibrium model could provide a candidate decision mechanism for testing apparent pricing anomalies.','A framework does not establish a single parsimonious account of every anomaly.','enabling')
a('ECO-02','FIN-08','Heterogeneous bounded-rational agents could provide a modeling representation for information-processing limits in markets.','A micro-to-macro framework does not resolve market efficiency or identify every observed mispricing.','enabling')
a('FIN-10','FIN-08','A predictability bound could be a consistency check for a candidate limited-information market model.','No bound is established here, and predictability is not an arbitrage or return guarantee.')
a('ECO-02','ECO-07','An explicit heterogeneous-agent representation could support a candidate labor matching/decision model.','It does not by itself explain the amplification target or produce reliable unemployment forecasts.','enabling')
a('FIN-05','FIN-02','A qualified liquidity-propagation mechanism could provide one channel in a systemic-crisis model.','It does not identify all crisis causes or establish reliable warning lead time.','enabling')
a('FIN-05','ECO-08','A micro-to-macro liquidity model could help specify a candidate funding-fragility channel in a banking model.','Liquidity dynamics alone do not describe money creation or provide a crisis-proof regulation design.')
a('ECO-08','FIN-02','A qualified banking-fragility mechanism could supply another scenario channel for systemic-risk tests.','Not all crises are banking events, and a model does not guarantee prevention.','enabling')
a('ECO-09','IND-10','A candidate welfare metric could help state the social outcome objective in a multi-objective comparison.','Aggregation remains normative and assumption-dependent; no impossibility theorem is asserted escaped.','enabling')
a('ECO-09','ECO-10','An explicitly scoped welfare objective could provide an efficiency benchmark for evaluating a public-goods mechanism.','A metric does not elicit truthful preferences or remove free riding.','enabling')
a('FIN-06','FIN-01','A qualified impact/risk identification method could supply one candidate factor class for pricing-model tests.','No ESG action is assumed to cause a premium, and one factor family does not explain all anomalies.')
a('ACT-01','ACT-10','Qualified mortality scenarios could be inputs to longevity-risk and funding calculations.','They do not guarantee lifetime income under arbitrary asset returns, demographics or resource constraints.','enabling')
a('ACT-01','ACT-06','Survival/cohort scenarios could supply one demographic input to a healthcare-utilization projection.','Mortality is not morbidity, treatment choice, cost inflation or a complete utilization model.','enabling')
a('MLC-06','ACT-02','A causal representation could help state candidate risk factors and identification assumptions for a pricing study.','Causal modeling does not remove confounding, choose fairness norms or establish regulatory approval.','enabling')
a('MLC-04','ACT-07','An inspectable model representation could provide an audit channel for a specified actuarial application.','Interpretability does not prove statistical fairness, robustness or legality across applications.','enabling')
a('ACT-03','ACT-08','An explicitly scoped aggregate risk measure could supply an objective or constraint in a risk-allocation model.','A risk metric does not supply feasible transfers, market responses or a socially optimal allocation.','enabling')
a('IND-10','ACT-08','A multi-objective method could help compare economic and social trade-offs in a proposed allocation.','Preferences, contracts and feasible market capacity remain separate; no global optimum is established.')
a('FIN-02','ACT-04','Candidate crisis mechanisms could motivate stress transitions included in a scenario generator.','A crisis theory is not a perfect multi-decade path generator or a reliable forecast.')
a('FIN-03','ACT-04','A safe-rate model could help state candidate constraints on interest-rate scenarios.','Historical explanation does not validate future-rate distributions or eliminate model uncertainty.','enabling')
a('ACT-04','ACT-10','Return and inflation scenarios could be inputs to tests of a retirement-income design.','A scenario generator cannot guarantee funding under every possible future; it may expose failure conditions.','enabling')
a('STR-09','ACT-05','Qualified state estimates for specified insured structures could inform a vulnerability component of a catastrophe-loss model.','A structural twin does not provide hazard probabilities, regional exposure or precise insurance losses.','enabling')
a('ECO-02','ACT-09','A heterogeneous decision model could supply candidate representations of policyholder responses under changing conditions.','It does not establish causal lapse, selection or moral-hazard behavior or an effective hedge.','enabling')
a('ACT-09','ACT-08','Qualified behavioral-response scenarios could be constraints in a proposed risk-transfer comparison.','Predicting responses does not establish a feasible, stable or optimal transfer system.')
a('ACT-08','ACT-10','A qualified risk-sharing model could help compare proposed allocation/pooling arrangements for retirement liabilities.','Risk transfer does not create resources or guarantee universal solvency without benefit cuts or external support.')
for id,reason in {
'ECO-03':'A universal aggregate-capital representation is not required by every heterogeneous-agent model; no specific valid restriction/construction links this resolution to another capability.',
'ECO-04':'An historical growth-divergence explanation does not supply a local innovation-productivity rule or a guaranteed development intervention.',
'ECO-05':'A savings/investment-correlation explanation does not supply the distinct market-liquidity, pricing or scenario mechanisms in this collection.',
'ECO-06':'No specified multi-currency path or intervention model connects this complete puzzle-resolution goal to another target; explanation alone is not a forecast generator.',
'FIN-04':'No qualified sovereign-contract/holdout mechanism is supplied. Incentive compatibility in a different public-goods problem cannot be transferred by assumption.',
'FIN-07':'The endogenous-money/run-fragility ambition substantially overlaps ECO-08; preserve the distinct source entry without a causal model-to-model alias arrow.',
'FIN-09':'The truthful global-public-goods provision target overlaps ECO-10, with an added market-funding constraint. No independent construction makes the complete goals a causal chain.'
}.items():u(id,reason,'overlapping-target' if id in ['FIN-07','FIN-09'] else 'unresolved-mechanism')
b.reject('ECO-04','IND-07','A historical growth explanation is not a quantitative law of local R&D productivity.')
b.reject('ECO-10','FIN-04','A public-goods mechanism does not automatically solve sovereign private-credit holdouts.')
b.reject('LON-09','ACT-01','Remaining healthspan measurement is not a validated 50-year population mortality model.')
b.branch('market-models','Market mechanisms and pricing models',['ECO-01','ECO-02','FIN-08','FIN-10','FIN-03','FIN-06','FIN-01','FIN-05','ECO-08','FIN-02'])
b.branch('risk-and-retirement','Risk, scenarios and retirement design',['ACT-01','ACT-03','ACT-08','ACT-09','ACT-04','ACT-10','FIN-02','FIN-03'])
b.branch('welfare-and-audit','Welfare objectives and model audit',['ECO-09','ECO-10','IND-10','MLC-04','ACT-07','MLC-06','ACT-02'])
b.save()
