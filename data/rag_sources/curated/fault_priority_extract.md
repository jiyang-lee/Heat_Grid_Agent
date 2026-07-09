---
document_title: Prioritisation of faults in district heating substations - Selected Extract
source_file: prioritisation_faults_substations.pdf
curated_file: fault_priority_extract.md
source_type: research_paper_pdf
rag_role: fault_priority_research
domain: district_heating_substation
language: en
page_start: 1
page_end: 9
download_url: https://publica.fraunhofer.de/bitstreams/07b656d0-fcae-4493-b84b-70a26a650c90/download
---

# Prioritisation of faults in district heating substations - Selected Extract

## Curation scope

- Included pages: 1, 4-9
- Extraction reason: Selected pages cover FMEA/O&M-FMEA rationale, occurrence/severity/monitoring/maintenance criteria, MPN calculation context, and high-priority fault ranking discussion.
- Excluded content: Excluded reference list, publication boilerplate, and pages without priority/fault-ranking content.

## Page 1: Prioritisation of faults in district heating substations: Towards predictive

Contents lists available at ScienceDirect
Energy
journal homepage: www.elsevier.com/locate/energy
Prioritisation of faults in district heating substations: Towards predictive
maintenance and optimised operation
Edison Guevara Bastidas a ,∗, Stefan Faulstich a , Holger Dittmer a, Martin Neumayer b,
Gowtham Sakthivel Mohan a , Kibriye Sercan-Calismaz c, Frank Hosenfelder d,
Thilo Glenewinkel d, Karsten Fischer-Florschütz e, Anna Cadenbach a
a Fraunhofer IEE, Joseph-Beuys-Straße 8, D-34117 Kassel, Germany
b Institut für nachhaltige Energieversorgung GmbH - INEV, Anton-Kathrein-Str. 1, D-83022 Rosenheim, Germany
c Der Energieeffizienzverband für Wärme, Kälte und KWK e. V. - AGFW, Stresemannallee 30, D-60596 Frankfurt am Main, Germany
d Enercity Netz GmbH, Auf der Papenburg 18 D-30459 Hannover, Germany
e YADOS GmbH, Yados-Straße 1 D-02977 Hoyerswerda, Germany
A R T I C L E I N F O A B S T R A C T
Keywords: Effectively detecting and handling faults in district heating substations is vital to ensure the security of heat
District heating substations supply and improve system efficiency. This is a challenging task due to the growing number of substations and
Predictive maintenance limited monitoring and service personnel. Digitalisation on the demand side offers an opportunity to develop
Operation optimisation data-driven methods for automatic fault detection, enabling utilities to optimise maintenance interventions
Fault detection methods
across multiple customers. A variety of different faults can occur in substations, which can reflect differently
FMEA
Prioritisation of faults
on operational data. It is then necessary to prioritise faults to address the most relevant ones in developing
adequate detection methods and supporting operators in their Operation and Maintenance (O&M) processes.
Failure Modes and Effects Analysis (FMEA) is a widely used methodology to prioritise potential failures,
but it misses aspects relevant to O&M. In this study, we propose an adaptation of the original FMEA for
the prioritisation of faults with focus on O&M optimisation. The methodology uses a Maintenance Priority
Number (MPN) for the ranking of faults based on severity, occurrence, monitoring potential and maintenance
capability of the fault. Severe and frequent faults, which have a potential to be monitored and maintained
yield the highest MPNs and should be in focus from an O&M perspective. Using the proposed methodology
the most relevant faults for predictive maintenance in substations in Germany have been identified. These are
the contamination of strainers, pump failures and fouling of heat exchangers. These faults should be in focus
when developing automatic fault detection and diagnosis methods.
1. Introduction benefits, the efficiency of district heating networks need to be increased
and the distribution temperatures decreased [4]. Current temperature
The first implementation of district heating in Germany took place levels in district heating networks account not only for the customers’
in the 1920s [1]. Over the years, these systems have undergone var- temperature demand but also for faults in the system [5]. Detecting
ious changes in heat supply, distribution, and consumption. While and correcting faults that increase the network return temperatures
the first implementations were typically fossil fuel-based, by gradually from substations is essential to achieving lower network supply temper-
reducing the operational temperatures from generation to generation,
atures, while decreasing distribution flows and increasing the overall
modern district heating systems enable an environmentally friendly and
efficiency of the system [6].
resource-saving heat supply by integrating industrial waste heat, re-
On the other hand, district heating systems can supply heat to thou-
newable energy sources, and combined heat and power plants [2]. Fur-
sands of consumers and the demand is increasing. The scenario ‘‘Kli-
thermore, they contribute to the large-scale integration of the increas-
maneutrales Deutschland 2045’’ (Climate neutral Germany 2045) [7]
ing deployment of intermittent renewable energy by combining the
various energy sectors, e.g., heat and electricity (sector coupling) [3]
foresees an increase from currently 15% to one third of households in
and using the associated potential for flexibility [4]. To achieve those Germany that will be supplied by district heating in the future. Due
∗ Corresponding author.
E-mail address: edison.guevara@iee.fraunhofer.de (E. Guevara Bastidas).
https://doi.org/10.1016/j.energy.2025.137210
Received 20 December 2024; Received in revised form 22 May 2025; Accepted 18 June 2025
Available online 1 July 2025
0360-5442/© 2025 The Authors. Published by Elsevier Ltd. This is an open access article under the CC BY license ( http://creativecommons.org/licenses/by/4.0/ ).

## Page 4: 3.1. The original FMEA methodology failure modes of the network pipelines, aiming to determine causes

3.1. The original FMEA methodology failure modes of the network pipelines, aiming to determine causes
and propose cost-effective, resource-aware solutions to increase the
Failure Mode and Effects Analysis (FMEA) is a systematic method reliability of the system. The methodology applied relies on occurrence
used to identify, evaluate, and prioritise potential failure modes within and severity as factors for the calculation of the RPN. In a more recent
a product, process, or system, while assessing the impact of these study, M. Valle et al. [21] apply an FMECA on district heating systems
failures on functionality and performance. The origins of this method to select relevant faults for simulation. As a result of the analysis the
trace back to the aerospace industry in the 1940s, where it was ini-
fouling of heat exchanger is selected as most relevant fault in substa-
tially employed to enhance reliability and safety. Over time, FMEA
tions. However, details about the implementation of the methodology,
has gained widespread acceptance across various sectors, including
to the authors knowledge, are not publicly available.
automotive, healthcare, and energy, due to its structured approach to
A key application of FMEA lies in the prioritisation of critical
risk assessment and mitigation [23]. The FMEA methodology can be
described as follows:
components for maintenance planning. Traditional FMEA emphasises
the probability of failure, the severity of its impact, and detectability.
1. First, the failure modes of the system under investigations are However, this approach can be enhanced by explicitly accounting for
determined. the influence of maintenance on failure probability. Certain compo-
2. Then, the probabilities of the failure modes Occurrences are nents may be more accessible for repair, thereby affecting their risk
assessed. These probabilities are then categorised and assigned prioritisation. It is also essential to distinguish between sudden failures
a scaling number, with the lowest number for the least probable and those that develop gradually over time, as this distinction can
category. inform more effectively condition monitoring strategies and targeted
3. The rate of Severity of each failure mode is assigned and scaled
maintenance actions. By weighting criteria such as failure development
due to the consequences of the failure and the amount of damage
patterns and intervention feasibility, FMEA can provide a more tailored
to the equipment.
risk assessment that aligns with the operational realities of wind farms.
4. Another scale number is assigned to the fault detection possibil-
In summary, while FMEA offers a robust framework for identifying and
ity or Detectability, with the lowest number to the most likely
addressing potential failures, its adaptability is crucial for maximising
detection of the failure.
its utility in specific domains. Tailored approaches enable a deeper
5. Finally, the outcome of the process is the Risk Priority Number
integration of maintenance strategies, consideration of environmental
(RPN) that is obtained by multiplying the three scale numbers
(see Eq. (1)). The failure modes are then ranked according to
factors, and advanced prioritisation methodologies. These refinements
their RPN, with the highest RPN corresponding to the most ultimately ensure that the methodology remains a cornerstone for
important failure. reliability and risk management in evolving industries.
𝑅𝑃 𝑁 = 𝑂𝑐𝑐𝑢𝑟𝑟𝑒𝑛𝑐𝑒 × 𝑆𝑒𝑣𝑒𝑟𝑖𝑡𝑦 × 𝐷𝑒𝑡𝑒𝑐𝑡𝑎𝑏𝑖𝑙𝑖𝑡𝑦 (1)
3.2. Adaptation of the original FMEA: the O&M-FMEA
FMEA is widely recognised for its capacity to enhance reliability by
identifying critical components that require focused monitoring. How- In order to prioritise faults that can actually be monitored and
ever, its adaptability to diverse applications is what makes it particu- which can be influenced by O&M measures, the original FMEA has been
larly powerful. In practice, FMEA is often tailored to address specific adapted. Occurrence and Severity are kept as important factors and
challenges and contexts, a flexibility that has already proven essential
Detectability has been replaced with a Monitoring & Maintenance
in industries such as wind energy. Wind turbines, whether onshore or
factor. For the ranking of failure modes a Maintenance Priority Num-
offshore, present unique challenges due to their complex systems and
ber (MPN) is introduced in contrast to the RPN of the original FMEA
exposure to varying climatic conditions. As a result, FMEA has been
(see Eq. (1)). The MPN is defined as shown in Eq. (2).
adapted in numerous ways to enhance its applicability in this sector.
For instance, FMEA has been employed to compare the reliability of 𝑀𝑃 𝑁 = 𝑂𝑐𝑐𝑢𝑟𝑟𝑒𝑛𝑐𝑒 × 𝑆𝑒𝑣𝑒𝑟𝑖𝑡𝑦 × 𝑀𝑜𝑛𝑖𝑡𝑜𝑟𝑖𝑛𝑔&𝑀𝑎𝑖𝑛𝑡𝑒𝑛𝑎𝑛𝑐𝑒 (2)
different turbine designs, thereby aiding in design improvements. [24]
effectively applied FMEA to evaluate the reliability of prospective wind The MPN is used to rank the failure modes, with the highest MPN
turbine designs. Additionally, [25] expanded FMEA to include main- corresponding to the most relevant failure for O&M optimisation and
tenance actions, facilitating a more integrated approach to reliability- predictive maintenance.
centred maintenance strategies. Furthermore, [26] compared FMEA
The adapted FMEA, or O&M-FMEA, focuses on supporting O&M
results for on-shore and offshore wind turbines, highlighting differences
optimisation from a technical perspective, by identifying relevant fail-
in risk factors influenced by environmental conditions. Another exten-
ure modes, which have the highest potential for the development of
sion of this method, Failure Modes, Effects, and Criticality Analysis
automatic detection systems for the early fault detection; and from
(FMECA), adds a criticality assessment to quantify the severity and
an organisational perspective, by helping district heating operators
likelihood of each failure mode [27]. FMECA has been performed
to prioritise component faults and hence focus their efforts in the
to optimise maintenance strategies by taking climatic conditions into
account, comparing geared and direct drive turbines [28]. The incor-
optimisation of their maintenance strategies.
poration of advanced techniques, such as fuzzy logic [29] and hybrid
cost-FMEA approaches [30], has further enhanced the analysis. More
3.2.1. Factors of the original FMEA
recent studies have introduced machine learning techniques to improve
The Occurrence represents the probability of the failure modes. The
FMEA applications in predictive maintenance, enabling real-time data
analysis and more accurate risk assessments [31,32].
probabilities are categorised and rated on a scale from 1 to 10, with 10
A. Rafati et al. [33] review reliability analysis techniques that have being the category for the highest probability. This factor accounts for
been applied on district heating systems. In the paper two studies about a prioritisation of frequent faults. The Severity of the failure mode is
FMEA in district heating are presented. The most relevant one is the assessed based on the potential or actual detrimental consequences of
work of P. Gilski et al. [34]. In their work the authors analysed ten-year the failure, and is rated on a scale from 1 to 10, with 10 being the
of failure and repair data from the Warsaw district heating network highest severity. This factor accounts for a prioritisation of faults with
using statistics and the FMEA method to identify key factors and critical high risk.

## Page 5: Occurrence scale for district heating substations.

Table 1 Table 2
Rating of the categories for monitoring potential: (5) a change in the component Rating of the categories for maintenance capability: (5) the fault can be prevented by
condition could be detected before the fault by existing instrumentation; (4) a change in timely refurbishment or repair; (4) the fault can be prevented by replacing a component
component condition could have been detected before the fault with additional effort; part; (3) the fault can be deferred by suitable operation; (2) the fault can be corrected
(3) the fault could be detected by existing instrumentation; (2) the detection of the by repair; (1) the fault can only be corrected by replacing the component.
fault requires additional efforts; (1) no fault detection possible. The highest monitoring Maintenance measure Before the fault After the fault
potential is given by rating 5.
Repair 5 2
Detection Before the fault After the fault No detection
Deferment 3
With existing instrumentation 5 3 Replacement 4 1
With additional effort 4 2
Table 3
Occurrence scale for district heating substations.
3.2.2. The monitoring & maintenance factor Occurrence
The third factor in the O&M-FMEA accounts for the handling po- Very frequent - every 1 year 10
tential on the fault during system operation. It is defined with two Every 2 years 9
concepts: the Monitoring Potential and the Maintenance Capability. Every 3 years 8
Every 4 years 7
From the perspective of O&M optimisation, interesting failure modes
Every 5 years 6
are those which can inherently be monitored either through appropri- Every 6 years 5
ate instrumentation or practicable inspection measures. For instance, Every 7 years 4
changes in the state of components due to degradation processes, which Unlikely - low likelihood but could occur at some time 3
can be detected through monitoring are more relevant than randomly
Rare - may only occur in exceptional circumstances 2
Extremely rare - has never or rarely happened 1
occurring failures. This is because the Monitoring Potential of the
failure is the basis for the development of data-driven methods for
early fault detection and in turn for predictive maintenance. The second Table 4
concept, Maintenance Capability, is related with the capability to
Severity scale for district heating substations.
prevent or correct the fault through maintenance measures. Faults that
Severity
can be prevented by means of preventive refurbishment or timely repair Risk of customer injury 10
offer more potential for predictive maintenance than those that can
M
M
a
a
t
t
e
e
r
r
i
i
a
a
l
l
d
d
a
a
m
m
a
a
g
g
e
e
t
t
o
o
c
u
u
ti
s
l
t
i
o
ty
mer 9
only be corrected. Therefore, the Monitoring & Maintenance factor Customer gets no heat 7
accounts for a prioritisation of faults with high monitoring potential Customer does not get enough heat 6
and high maintenance capability. – Separation between faults and efficiency losses – 5
The Monitoring & Maintenance factor is calculated according Poor control (e.g. slightly oscillating control of ± 5K) 4
Unsuitable load profile (unsuitable heating curve, unsuitable time schedule) 3
to Eq. (3).
Efficiency losses 2
√ No noticeable effect 1
𝑀𝑜𝑛𝑖𝑡𝑜𝑟𝑖𝑛𝑔&𝑀𝑎𝑖𝑛𝑡𝑒𝑛𝑎𝑛𝑐𝑒 = 2 × 𝑀𝑜𝑛𝑖𝑡𝑜𝑟𝑖𝑛𝑔 × 𝑀𝑎𝑖𝑛𝑡𝑒𝑛𝑎𝑛𝑐𝑒 (3)
The factor 2 is included, so that all three factors, Severity, Occur-
rence and Monitoring & Maintenance have a range to a maximum
3.3. Rating scale for district heating substations
of 10. This produces a maximum possible MPN of 1000, which is
consistent with other FMEA implementations.
Together with industry experts, the assessment criteria and rating
Monitoring potential. The monitoring potential of a fault is categorised scale for the Occurrence and Severity factors to be applied to district
and assigned a rating on a scale from 1 to 5 according to Table 1. heating substations have been defined. The Occurrence factor is based
The categorisation follows the criteria that failure modes, which can on the frequency of the failure mode per single substation and is cate-
potentially be detected before the failure occurs have higher rating gorised on a scale from 1 to 10, with 10 being the highest frequency. As
than those which can only be detected after the fault. Additionally, a
can be seen in the scale definition in Table 3, a rating of 10 corresponds
second criteria categorises failure modes depending on the detection
to faults that happen every year, whereas a rating of 1 corresponds to
efforts or costs required. Failure modes or faults, which can potentially
extremely rare faults, that has never or rarely happened.
be detected by existing instrumentation have higher rating than those
The Severity of the failure mode is assessed based on the potential
that require additional efforts to detect e.g., installation of additional
or actual detrimental consequences of the failure, not only in terms
instrumentation for the monitoring of system variables not yet covered
of safety and damage to equipment, but also considering the effect
or manual inspection of the related component.
on efficiency losses. It is also rated on a scale from 1 to 10, with
10 being the highest severity (Table 4). The rating scale differentiates
Maintenance capability. The maintenance capability is categorised and, between actual faults on the upper part of the scale, which can yield
similarly to the monitoring potential, assigned a rating on a scale from 1 into interruption of the heat supply or even pose a risk of injury at the
to 5, as presented in Table 2. The categorisation criteria is also twofold. highest rating and faults that only have an effect on the performance
On the one hand, degradation processes that can be mitigated by or efficiency of the system, which are located on the lower part of
preventive maintenance (e.g. adjustment, lubrication, corrosion protec- the scale. A rating of 5 in severity is not used. This builds a needed
tion, cleaning, repair, replacement of component part), hence avoiding gap between the faults and efficiency losses, in order to separates both
a failure (before the fault), get a higher rating than faults that can only effects more clearly.
be corrected (after the fault). On the other hand, it is differentiated
between repair, deferment and replacement activities, whereby faults 3.4. Relevant faults in district heating substations
that can be handled by refurbishment or repair measures get a higher
rating than faults that demand replacement of components or parts To apply the previously described O&M-FMEA methodology to the
of it. In the middle of the rating scale are faults that can be delayed use case of district heating substations in Germany, the relevant faults
(deferment) to be corrected at a later time, by means of suitable oper- need to be identified and structured.
ation (e.g. deferment of heat exchanger fouling, by means of suitable To identify relevant faults in substations a literature review has
operation, for a replacement at a later time). been conducted (see 2.2) and the faults have been associated with the

## Page 6: Fig. 2. Excerpt of the faults in substations grouped by the affected component and coloured by fault type.

Fig. 2. Excerpt of the faults in substations grouped by the affected component and coloured by fault type.
affected components in a preliminary list. Previous research work is range of professional expertise. Emphasising quality, the survey was
mainly based on substations in district heating networks of Sweden and designed to get in-depth responses.
Denmark. In a workshop with industry experts of Germany, the pre- After the data collection and pre-processing, the following pro-
liminary list has been extended, including the experiences in German cedure was carried out for the ranking of faults: firstly, the mean
district heating. occurrence, severity, monitoring potential and maintenance capability
The O&M-FMEA methodology described in this study, in contrast was computed for each fault over all participants; secondly, an MPN for
to the original FMEA, omits an extensive analysis of all possible faults, each fault was calculated based on the computed means of the different
their effects on the functionality, connections between components factors and using Eqs. (2) and (3); and thirdly, faults were ranked
and their relations. Instead, only faults actually occurring in practice according to the calculated MPN. By calculating first the means of the
are considered, since from an O&M point of view, only faults with a individual factors, the method accounts for the different subjectivity
minimum of occurrence are relevant. An excerpt of all identified faults among the participants to get a mean opinion on the different factors.
grouped by the affected component is presented in Fig. 2. The identified The use of mean over median is also preferred, in order to consider all
faults cover installation errors (dark orange), wrong settings (grey) participant’s rating the same way and to not exclude any outlier. The
and actual faults during operation (light orange). On the other hand, list of faults ranked according to the calculated MPN is shown in Table
it is differentiated between components installed on the primary and A.5 together with the mean occurrence, severity, monitoring potential
secondary side. The full list, containing a total of 81 faults, including and maintenance capability used for the calculation.
the affected component and a short description, is presented in Table
A.5. 4. Prioritisation of faults
3.5. Survey study Fig. 3 shows the frequency distribution of the MPNs presented in
Table A.5, as a result of the survey. The histogram shows a right-skewed
By means of a survey study, German practitioners were asked to distribution with a tail containing few faults with the highest MPNs.
evaluate each one of the identified 81 faults in substations using the Fig. 4 shows the results for the 10 highest ranked faults. As can be
defined rating criteria for Occurrence, Severity, Monitoring Poten- seen in the figure, the occurrence rating (blue bar) goes from 4.3 to
tial and Maintenance Capability. The survey study is conceived as 6.1, meaning a frequency of fault of 5 to 7 years for those faults. The
an online questionnaire covering four scales (one separate scale per severity rating (orange bar) goes from 5.6 to 7.5, meaning the faults
each rating criteria) for each fault and space for comments, requiring a have an effect on the delivery of heat to the customer, partially or even
total of around 1.5 h from each of the 13 participating German experts. completely.
Each participating expert belong to either one of the groups Operator, There are different types of faults present in the table. Two faults
representative from Expert Associations or OEM, ensuring a diverse are not related with O&M: incorrect parameterisation of the control

## Page 7: Monitoring & Maintenance potential: air in the piping system has a This study has presented a novel methodology for the prioritisation

Fig. 3. Frequency distribution of MPNs.
unit and the wrong placement of the outdoor temperature sensor. 5. Conclusions
Other faults, which are at the bottom of the list, have a relative low
Monitoring & Maintenance potential: air in the piping system has a This study has presented a novel methodology for the prioritisation
monitoring potential (grey bar) of 2.1, meaning it can only be detected of faults, aimed at supporting the optimisation of O&M. The methodol-
after the fault occurred and only with additional efforts; and two faults ogy, which is based on the FMEA process, introduces a monitoring and
associated with the three-way valve for domestic hot water have a maintenance evaluation factor. Based on a literature review of previous
maintenance capability (yellow bar) of around 2, meaning they can research, the relevant faults of district heating substations in the north
be repaired but only through corrective actions after fault occurred. European countries have been extended including the experiences in
And finally, 5 faults have a high potential for predictive maintenance. German district heating. The rating criteria for substations has been
These are poor flow rate through the strainer on both the primary defined, and the methodology has been applied on all identified faults
and the secondary side, failure of the heating circuit pump, failure by means of a survey study with the participation of German practition-
of the storage charging pump for domestic hot water and the fouling ers. In the survey study all faults have been evaluated according to their
of heat exchangers. These faults have a Monitoring Potential in the occurrence, severity, monitoring potential and maintenance capability,
range from 3.6 (contamination of the strainer on the secondary side) and ranked according to the calculated priority indicator MPN. The 10
to 4.2 (fouling of heat exchanger), meaning a detection before fault is faults with the highest MPNs have been discussed in detail, considering
possible and a Maintenance Capability in the range from 2.6 (failure their impact on O&M optimisation.
of the heating circuit pump) to 4.2 (contamination of the strainer on The study has identified relevant faults for predictive maintenance,
the primary side), meaning a deferment of the fault or even preventive these are the contamination of strainers, failure of the heating circuit
actions are possible. pump, failure of the storage charging pump for domestic hot water and
The information gathered in the comments field of the survey help the fouling of heat exchangers. These faults and their failure modes
to further interpret the survey results. For instance, one participant need to be further investigated to support the development of early
argued that cleaning a brazed heat exchanger only works in an ultra- fault detection methods.
sonic bath, which is often more expensive than a new heat exchanger. The study has identified relevant faults with low monitoring and
This supports the obtained maintenance capability for the fouling of maintenance potential, these are air in the piping system and defective
heat exchanger of 3.2, meaning the fault can be deferred by suitable actuator or valve of the domestic hot water electric 3-way valve. In this
operation. If the preventive action of cleaning the heat exchanger is case, operators need to develop organisational measures to optimise
not economically feasible, then the next best strategy would be to defer O&M, like strategies to prevent or correct relevant faults and optimal
the fault for the replacement of the component at a convenient time logistics and supply chain management.
(i.e. out of the heating period in case of a heat exchanger in the heating The study has identified relevant faults that are not related to
circuit). O&M, these are the incorrect parameterisation of control unit and
Other comments concerned the ambiguity of some fault descrip- wrong placement of outdoor temperature sensor. In this case, utilities
tions. While some of those fault descriptions were corrected and need to develop adequate strategies for installation, commissioning and
rephrased in a more concrete way during the survey study, some others auto-commissioning.
remained ambiguous, that is the case of the failures of the pumps. A Since the results reflect the general situation in district heating
failure of the pump can be many different things and can have different substations in Germany, the recommendations presented here are par-
causes: can be a failure of the motor (e.g. rotor is blocked), a failure in ticularly relevant for district heating operators in Germany and for
the pump itself (e.g. wearing or blockage of the impeller) or an issue researchers and developers working on fault detection methods with
with the sensors or electronics. Each fault of the list in Table A.5 can a focus on the German market. At the same time, the results lay the
potentially be further divided into specific faults, making it longer and foundation for the design of experimental set-ups to further investigate
more complex to evaluate. Therefore, the level of detail covered in in detail the failure modes of the identified relevant faults, in the
the list is considered appropriate. Prioritised faults, such as the failure context of the research project PreDist ‘‘Predictive Maintenance for
of the heating circulation pump and failure of the charging pump for District Heating’’, founded by the Federal Ministry of Economic Affairs
domestic hot water, can and should be further investigated to identify and Climate Action of Germany.
relevant failure modes in order to support the development of fault Furthermore, this study presents a novel methodology that can
detection methods. be directly applied to evaluate substations in other district heating
There has been no limitations to the substation typology when scenarios, e.g. substation in other countries. At the same time, the
asking the German practitioners. Hence, the results of the prioritisation methodology can be easily adapted to other areas of the industry to
reflect the general situation of district heating substations in Germany. prioritise faults and support in the optimisation of O&M strategies.

## Page 8: monitoring potential (grey) and maintenance capability (light orange).

Fig. 4. Prioritised faults in district heating substations with MPN results. To the right of each fault there is a bar chart showing: occurrence (blue), severity (dark orange),
monitoring potential (grey) and maintenance capability (light orange).
Table A.5
List of faults in district heating substations along with the affected component and their occurrence (Occ), severity (Sev), monitoring potential (Mon) maintenance capability (Main)
ratings ranked by their maintenance priority number (MPN). Displayed values are rounded, which might result in slight deviations when recalculating the MPN.
Rank Component Fault description MPN Occ Sev Mon Main
1 Strainer (primary side) Poor flow rate (strainer contaminated) 326 5.8 7.0 3.9 4.2
2 Strainer (secondary side) Poor flow rate (strainer contaminated) 294 5.8 6.5 3.6 4.1
3 Heating circuit pump Failure of the heating circuit pump 237 5.0 7.5 3.8 2.6
4 Domestic hot water storage charging pump Failure of the domestic hot water storage charging pump 234 5.1 7.3 3.7 2.8
5 Control unit Incorrect parameterisation 230 5.2 6.1 4.0 3.3
6 Heat exchanger Poor heat transfer, poor flow (contamination) 212 4.8 6.0 4.2 3.2
7 Piping system Air in the piping system 198 6.1 6.7 2.1 2.8
8 Domestic hot water electric 3-way valve Actuator of the domestic hot water electric 3-way valve defective 192 4.9 6.8 3.5 2.3
9 Outdoor temperature sensor Outdoor temperature sensor in the wrong place 171 4.3 5.6 4.2 3.0
10 Domestic hot water electric 3-way valve Valve of the domestic hot water electric 3-way valve defective 170 5.3 6.5 3.3 1.9
11 Expansion vessel Low pre-charge at the expansion vessel 160 4.9 5.0 2.9 3.6
12 Domestic hot water circulation pump Circulation flow rate too low (e.g. inadequate hydronic balancing of 142 4.3 5.8 3.2 2.5
domestic hot water circulation circuit)
13 Domestic hot water circulation pump Failure of domestic hot water circulation pump 142 4.1 5.5 3.4 2.9
14 Pressure reducer (direct substation) Pressure fluctuations in the system 141 3.0 7.5 3.1 3.1
15 Motorised control valve (primary side) Actuator defective 140 3.6 7.4 3.4 2.0
16 Control unit Control unit defective 138 4.0 6.5 3.5 2.0
17 Differential pressure regulator Incorrect setting of the differential pressure regulator 138 4.3 5.3 3.1 2.9
18 Motorised control valve (3-way valve, Actuator defective 131 4.1 6.1 3.2 2.1
secondary side)
19 Motorised control valve (primary side) Oversized control valve (inadequate valve authority) 129 4.3 5.8 3.3 2.0
20 Differential pressure regulator Differential pressure regulator jams when closed 127 3.4 6.8 3.3 2.3
21 Temperature sensor (secondary side) Temperature sensor is defective and gives no signal 125 3.3 6.4 3.5 2.5
22 Temperature sensor (primary side) Temperature sensor gives wrong signal 124 3.3 6.2 3.4 2.7
23 Domestic hot water circulation pump Domestic hot water circulation flow rate too high (e.g. due to 123 4.5 4.4 3.3 3.0
inadequate hydronic balancing of domestic hot water circulation
circuit)
24 Heat exchanger Incorrect design: flow rate too high for the heat exchanger, low 119 3.8 5.9 3.2 2.2
heat transfer
25 Heat exchanger Leakage, inside (cracking) 118 3.3 7.2 2.8 2.2
26 Motorised control valve (primary side) Control valve jams when closed 116 3.5 6.6 3.2 1.9
27 Temperature sensor (primary side) Temperature sensor in the wrong place 115 3.3 5.6 3.2 3.0
28 Safety relief valve Water loss, does not close properly 113 3.9 6.9 2.0 2.2
29 Volume flow limiter Incorrect setting of the volume flow limiter 112 3.4 4.8 3.5 3.4
30 Outdoor temperature sensor Outdoor temperature sensor is defective and does not give a signal 112 3.4 5.1 4.2 2.5
31 Volume flow controller Incorrect setting of the volume flow controller 111 3.2 5.0 3.5 3.5
32 Pressure independent control valve Actuator defective 110 3.2 6.7 3.3 2.0
33 Safety temperature limiter Safety temperature limiter defective 110 3.0 8.1 2.4 2.1
34 Outdoor temperature sensor Outdoor temperature sensor is giving the wrong signal 108 2.9 5.7 3.6 2.9
35 Shut-off valve Shut-off valve closed 108 2.4 7.4 2.8 3.4
(continued on next page)

## Page 9: 36 Motorised control valve (primary side) Incorrect setting of the actuator travel time in the control unit 107 4.0 4.5 3.3 2.6

Table A.5 (continued).
Rank Component Fault description MPN Occ Sev Mon Main
36 Motorised control valve (primary side) Incorrect setting of the actuator travel time in the control unit 107 4.0 4.5 3.3 2.6
37 Temperature sensor (secondary side) Temperature sensor gives wrong signal 107 3.3 6.0 3.0 2.5
38 Motorised control valve (primary side) Control valve jammed in open state (imminent danger if type-tested 106 2.2 9.0 3.6 2.0
unit with safety function)
39 Temperature sensor (primary side) Temperature sensor is defective and gives no signal 106 3.5 4.7 3.6 2.7
40 Safety temperature monitor Safety temperature monitor defective 105 3.1 7.9 2.6 1.8
41 Shut-off valve Leakage, external 104 3.0 7.2 2.1 2.8
42 Motorised control valve (primary side) External leakage (e.g. stuffing box leaking, seal leaking) 103 3.5 6.9 1.5 3.0
43 Control unit Incorrect control sequence (incorrect connection) 100 2.5 6.7 3.1 2.9
44 Heat exchanger Leakage, external 100 3.0 7.5 2.0 2.5
45 Motorised control valve (3-way valve, External leakage (e.g. stuffing box leaking, seal leaking) 99 3.5 6.7 1.6 2.8
secondary side)
46 Pressure independent control valve Differential pressure regulator jams when closed 96 2.9 6.9 2.9 2.0
47 Pressure independent control valve Incorrect setting of the actuator travel time in the control unit 94 3.8 4.2 3.2 2.7
48 Motorised control valve (3-way valve, Oversized control valve (inadequate valve authority) 92 4.3 4.8 3.1 1.7
secondary side)
49 Temperature monitor/controller Temperature monitor/controller defective 88 2.8 7.0 3.0 1.8
50 Pressure reducer (direct substation) Diaphragm rupture: Leakage to the outside 85 2.5 7.6 2.0 2.5
51 Motorised control valve (primary side) Control valve leaking when closed (leakage volume above standard) 85 2.9 5.0 3.4 2.5
52 Motorised control valve (3-way valve, Control valve jammed when closed 84 3.2 5.8 2.9 1.8
secondary side)
53 Expansion vessel No pre-charge (membrane rupture) 84 2.8 6.2 2.5 2.4
54 Differential pressure regulator Differential pressure regulator jams when open 84 2.9 5.0 3.2 2.6
55 Pressure independent control valve Control valve jammed when open (imminent danger if type-tested 81 2.0 8.1 3.1 2.0
unit with safety function)
56 Motorised control valve (primary side) Actuator cannot change the position of the valve (incorrectly 78 2.0 7.7 3.6 1.8
designed)
57 Safety relief valve does not open, risk of over-pressure 78 2.0 9.5 1.9 2.2
58 Pressure independent control valve Incorrect setting of volume flow limiter 76 2.8 4.8 3.0 2.6
59 Pressure reducer (direct substation) Incorrect setting 76 1.8 8.3 2.8 2.2
60 Temperature sensor (secondary side) Temperature sensor in the wrong place 72 2.5 5.2 2.7 2.8
61 Motorised control valve (3-way valve, Control valve leaking when closed 72 3.0 5.4 2.8 1.8
secondary side)
62 Shut-off valve Leakage inside 70 2.8 5.5 2.1 2.4
63 Motorised control valve (3-way valve, Incorrect actuator travel time (built-in actuator does not match the 70 3.2 4.4 3.0 2.0
secondary side) travel time set in the control unit)
64 Motorised control valve (3-way valve, Control valve jammed when open 70 2.6 5.6 2.9 2.1
secondary side)
65 Pressure independent control valve External leakage (e.g. stuffing box leaking, seal leaking) 62 2.7 5.6 1.6 2.7
66 Motorised control valve (primary side) Incorrect actuator installed (travel time not suitable in the context 61 3.1 4.5 3.1 1.5
of the control circuit)
67 Pressure independent control valve Control valve jammed when closed 61 2.4 5.5 3.0 1.8
68 Pressure independent control valve Oversized control valve (inadequate valve authority) 61 2.6 5.1 2.7 2.0
69 Motorised control valve (3-way valve, Poor connection between actuator and valve (force-fit) 54 2.3 5.1 2.0 2.6
secondary side)
70 Motorised control valve (primary side) Poor connection between actuator and valve (form-fit) 54 2.3 5.2 2.2 2.3
71 Motorised control valve (primary side) Poor connection between actuator and valve (force-fit) 53 2.3 5.1 2.2 2.3
72 Motorised control valve (3-way valve, Actuator cannot change the position of the valve (incorrectly 53 2.2 5.2 2.9 1.8
secondary side) designed)
73 Pressure independent control valve Actuator cannot change the position of the valve (incorrectly 50 1.9 5.8 3.2 1.6
designed)
74 Motorised control valve (3-way valve, Poor connection between actuator and valve (form-fit) 48 2.4 4.3 2.0 2.6
secondary side)
75 Pressure independent control valve Control valve leaks when closed 44 2.1 4.1 3.0 2.2
76 Pressure independent control valve Poor connection between actuator and valve (force-fit) 43 1.9 4.7 2.1 2.8
77 Thermal energy meter Leakage outside (leaking) 41 2.0 4.9 1.7 2.5
78 Pressure independent control valve Poor connection between actuator and valve (form-fit) 41 1.8 4.7 2.1 2.8
79 Pressure independent control valve Incorrect actuator installed (travel time not suitable in the context 41 2.1 4.3 3.0 1.7
of the control circuit)
80 Thermal energy meter Failure of the thermal energy meter 24 2.4 2.1 3.2 1.8
81 Thermal energy meter Gateway defective 23 2.4 1.9 3.6 1.8
CRediT authorship contribution statement Frank Hosenfelder: Writing – review & editing, Validation, Resources,
Methodology. Thilo Glenewinkel: Writing – review & editing,
Edison Guevara Bastidas: Writing – original draft, Visualization, Validation, Resources, Methodology. Karsten Fischer-Florschütz:
Validation, Software, Methodology, Investigation, Formal analysis, Data Writing – review & editing, Validation, Resources, Methodology.
curation, Conceptualization. Stefan Faulstich: Writing – review & Anna Cadenbach: Writing – review & editing, Resources, Project
editing, Writing – original draft, Validation, Supervision, Methodology, administration, Funding acquisition.
Investigation, Conceptualization. Holger Dittmer: Writing – review
& editing, Writing – original draft, Validation, Formal analysis. Declaration of competing interest
Martin Neumayer: Writing – review & editing, Writing – original
draft, Visualization, Validation. Gowtham Sakthivel Mohan: Writing The authors declare that they have no known competing finan-
– review & editing, Investigation, Data curation, Conceptualization. cial interests or personal relationships that could have appeared to
Kibriye Sercan-Calismaz: Writing – review & editing, Investigation. influence the work reported in this paper.
