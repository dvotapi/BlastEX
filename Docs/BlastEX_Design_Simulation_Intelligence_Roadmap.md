# BlastEX Design, Simulation & Intelligence Roadmap

---

# ENGLISH VERSION

## Goal

Evolve BlastEX from a blast-calculation and first-generation blast-design application into a complete engineering platform for:

```text
DESIGN
  ↓
PREDICT
  ↓
OPTIMISE
  ↓
EXECUTE
  ↓
MEASURE
  ↓
LEARN
  ↓
RECOMMEND
```

BlastEX should combine:

- blast design;
- spatial bench and geology modelling;
- charging design;
- initiation design;
- fragmentation prediction;
- vibration prediction;
- blast-movement approximation;
- cost modelling;
- execution tracking;
- post-blast measurements;
- machine-learning calibration;
- site-specific prediction;
- multi-objective design recommendation.

The long-term objective is:

> **BlastEX learns from every blast and uses site-specific engineering history to propose safer, cheaper and more predictable future blast designs.**

The system must remain an engineering decision-support platform.

ML must never silently modify or approve an engineering design.

---

# 1. Core Engineering Architecture

The central engineering workflow must be:

```text
Mine Site
   ↓
Bench / Geological Data
   ↓
Blast Design
   ↓
Physics / Empirical Simulation
   ↓
ML-Corrected Prediction
   ↓
Scenario Optimisation
   ↓
Engineering Approval
   ↓
As-Drilled
   ↓
As-Charged
   ↓
As-Fired
   ↓
Post-Blast Measurements
   ↓
Training Dataset
   ↓
Mine-Specific Models
   ↓
Future Recommendations
```

BlastEX must distinguish four types of information:

```text
DESIGNED
EXECUTED
PREDICTED
MEASURED
```

These must never overwrite each other.

Example:

```text
HoleDesign
HoleAsDrilled
HoleAsCharged
HoleAsFired
```

and:

```text
PredictedFragmentation
MeasuredFragmentation
```

must remain separate domain entities.

---

# 2. Site-Level Architecture

Introduce a first-class mine/site aggregate.

Suggested model:

```python
MineSite:
    id
    name
    coordinate_system
    benches
    geological_domains
    blast_designs
    measurements
    calibration_sets
    model_registry
```

ML models must be associated with a site.

Example:

```text
Mine A
 ├── fragmentation model v6
 ├── vibration model v3
 ├── oversize model v4
 └── cost-outcome model v2
```

A model trained for one mine must not automatically be treated as valid for another mine.

---

# 3. ML Strategy

Do not build an AI system that directly outputs a blast pattern without engineering constraints.

Use a hybrid architecture:

```text
Engineering Models
        +
Historical Data
        +
Machine Learning
        ↓
Outcome Prediction
        ↓
Optimisation
        ↓
Recommended Alternatives
```

The recommended approach is:

```text
Physics / empirical baseline
        ↓
ML correction
        ↓
Site-calibrated prediction
```

Example:

```text
Kuz-Ram prediction:
X50 = 380 mm

Site ML correction:
-52 mm

BlastEX prediction:
X50 = 328 mm
```

---

# 4. ML Maturity Levels

## Level 0 — Data Foundation

No ML prediction yet.

BlastEX only ensures that each blast produces structured training data.

Required immediately.

---

## Level 1 — Site Calibration

ML corrects existing empirical models.

Examples:

```text
Kuz-Ram → calibrated fragmentation
Scaled-distance PPV → calibrated vibration
```

This is the preferred first production ML capability.

---

## Level 2 — Outcome Prediction

ML predicts blast outcomes directly from design, geology and execution data.

Targets may include:

```text
X20
X50
X80
oversize %
PPV
frequency
toe risk
backbreak
secondary breaking
muckpile characteristics
```

---

## Level 3 — Design Recommendation

BlastEX generates candidate engineering designs and ML predicts the outcomes.

```text
Candidate Generator
      ↓
Engineering Constraints
      ↓
Physics / Empirical Models
      ↓
ML Predictions
      ↓
Cost Engine
      ↓
Multi-Objective Optimiser
      ↓
Recommended Alternatives
```

---

## Level 4 — Cross-Blast Learning

The platform continuously learns from completed blasts.

Models are retrained only through controlled model-training workflows.

Never implement uncontrolled online learning directly in production calculations.

---

# PHASE BDX-001 — Spatial Foundation and Surface Model

## Goal

Build the spatial foundation required for professional blast design.

### Scope

Introduce:

```text
CoordinateSystem
SurfaceModel
TIN
TopSurface
FloorSurface
FaceSurface
PostBlastSurface
```

Support:

```text
XYZ
CSV
DXF
GeoJSON
```

Minimum first-class support:

```text
XYZ point cloud
CSV survey points
DXF points
DXF polylines
```

Surface operations:

```text
elevation_at(x, y)
line_intersection()
vertical_intersection()
distance_to_surface()
```

Generated collars must follow the real terrain.

Hole depths may be calculated relative to the floor surface.

Retain compatibility with the current planar BenchSurface model.

### Acceptance Criteria

BlastEX can import a surveyed bench, define a blast block and generate holes whose collar elevations follow the real top surface.

---

# PHASE BDX-002 — Geological Domains and Hole Intercepts

## Goal

Make blast design spatially dependent on geology.

Introduce:

```python
BlastDomain
HoleInterval
WaterInterval
RockPropertySet
```

Support geological attributes such as:

```text
density
UCS
fracturing
RQD
Young's modulus
Poisson ratio
P-wave velocity
joint spacing
joint orientation
blastability
water condition
```

Not all properties must be mandatory.

Example hole:

```text
0–3 m    weathered
3–8 m    competent granite
8–11 m   fractured granite
```

Charging and simulation engines must be capable of consuming these intervals later.

---

# PHASE BDX-003 — Professional Pattern Design

## Goal

Upgrade regular pattern generation into production blast design.

Support:

```text
square
rectangular
staggered
variable pattern
domain-dependent pattern
```

Add hole types:

```text
production
buffer
trim
presplit
contour
stab
satellite
infill
```

Implement:

```text
variable first-row burden
true face burden
toe burden
collar burden
local burden
local spacing
manual hole insertion
manual hole movement
toe editing
depth editing
inclination editing
azimuth editing
```

Provide engineering maps:

```text
burden
spacing
hole depth
subdrill
bench height
toe burden
collar burden
```

---

# PHASE BDX-004 — Charging Rules Engine

## Goal

Turn charging into a spatial rule-based engineering system.

Introduce:

```python
ChargeTemplate:
    conditions
    actions
    priority
```

Conditions may depend on:

```text
hole type
row
depth
diameter
burden
spacing
rock domain
geological interval
water
distance to face
target PF
```

Support:

```text
stemming
bulk explosive
packaged explosive
air deck
inert deck
water deck
primer
booster
detonator
```

Allow multiple explosives inside one hole.

Example:

```text
bottom → high-density emulsion
dry column → ANFO
wet interval → water-resistant emulsion
```

Introduce explicit primer objects.

---

# PHASE BDX-005 — Initiation Network Engine 2.0

## Goal

Build an editable timing and initiation engine.

Introduce:

```text
Detonator
SurfaceConnector
DownholeConnector
DetonatingCord
Starter
ElectronicChannel
FiringEvent
```

Support manual tie editing.

Support electronic timing by:

```text
row
selection
direction
gradient
V pattern
diagonal pattern
custom timing expression
```

Do not use unsafe Python `eval`.

Support:

```text
hole-level timing
deck-level timing
primer-level timing
```

Diagnostics:

```text
unconnected holes
duplicate times
unexpected firing order
high MIC
insufficient delays
relief-direction problems
isolated network branches
```

Add a timing animation showing firing sequence and timing isolines.

---

# PHASE BDX-006 — Fragmentation Simulation

## Goal

Integrate the current BlastEX fragmentation calculations with spatial blast design.

Create:

```text
simulation/
    fragmentation/
```

Separate the fragmentation model from the legacy calculation facade.

Support initially:

```text
Kuznetsov
Kuz-Ram
Swebrec
```

For each local influence region calculate:

```text
X20
X50
X80
oversize %
distribution curve
```

Inputs may include:

```text
local burden
spacing
bench height
diameter
explosive
energy
charge mass
stemming
rock properties
```

Provide heatmaps:

```text
X50
X80
oversize
powder factor
```

Every prediction must expose:

```text
model
model version
inputs
parameters
calibration
```

---

# PHASE BDX-007 — Vibration and Receptors

## Goal

Develop calibrated site vibration modelling.

Introduce:

```python
Receptor
VibrationModel
VibrationMeasurement
```

Receptor examples:

```text
building
pipeline
crusher
highwall
power line
monitoring station
```

Support explicit site laws:

```text
PPV = K × SD^n
```

Store:

```text
K
n
scaled-distance convention
calibration source
confidence
```

Never silently mix different scaled-distance definitions.

Calculate event-based MIC with configurable windows.

---

# PHASE BDX-008 — As-Drilled Integration

## Goal

Record actual drilling and compare it with design.

Introduce:

```python
AsDrilledHole:
    design_hole_id
    actual_collar
    actual_toe
    actual_depth
    actual_diameter
    survey_points
```

Calculate:

```text
collar offset
toe offset
depth deviation
angle deviation
azimuth deviation
actual burden
actual spacing
```

Prepare MWD import structure for:

```text
depth
penetration rate
rotation pressure
feed pressure
torque
air pressure
```

The core must remain manufacturer-neutral.

---

# PHASE BDX-009 — As-Charged and As-Fired

## Goal

Create the execution record.

Store actual:

```text
explosive product
charge mass
deck depths
stemming
primer position
detonator
programmed time
verified time
loading timestamp
firing timestamp
```

Provide comparisons:

```text
Design vs Drilled
Design vs Charged
Design vs Fired
```

---

# PHASE BDX-010 — Post-Blast Measurements

## Goal

Close the engineering feedback loop.

Introduce:

```python
BlastResult:
    design_id
    fragmentation
    vibration
    muckpile
    backbreak
    toe_condition
    flyrock_observations
    secondary_breaking
    cost_actual
```

Support measured:

```text
P20
P50
P80
oversize
PPV
frequency
backbreak
toe condition
muckpile dimensions
```

Calculate:

```text
predicted vs measured
designed vs actual
planned cost vs actual cost
```

This phase is mandatory before meaningful advanced ML.

---

# PHASE BDX-011 — ML Data Foundation

## Goal

Turn completed blasts into versioned training datasets.

Create:

```text
intelligence/
    datasets/
        features.py
        targets.py
        builder.py
        validation.py
```

Each training sample must contain provenance.

Example feature groups:

```text
SITE
GEOLOGY
GEOMETRY
CHARGING
TIMING
EXECUTION
ENVIRONMENT
```

Targets:

```text
FRAGMENTATION
VIBRATION
BLAST PERFORMANCE
ECONOMICS
```

Store:

```text
feature_schema_version
dataset_version
source_blast_ids
created_at
site_id
```

Never train directly from mutable production records.

Training datasets must be immutable snapshots.

---

# PHASE BDX-012 — Site Calibration Models

## Goal

Deploy the first useful production ML.

ML adjusts engineering-model predictions.

Examples:

```text
Kuz-Ram residual correction
PPV residual correction
oversize correction
```

Recommended algorithms for early datasets:

```text
CatBoost
XGBoost
LightGBM
Random Forest
Extra Trees
```

Do not use neural networks by default.

For tabular mine data, tree-based models should be the baseline.

Each model must have:

```text
site_id
model_type
model_version
training_dataset_version
feature_schema_version
training_date
metrics
status
```

---

# PHASE BDX-013 — Outcome Prediction

## Goal

Predict blast outcomes directly.

Potential targets:

```text
X50
X80
oversize
PPV
frequency
toe probability
backbreak
secondary breaking
muckpile spread
cost impact
```

Initially use separate specialised models rather than one universal model.

Example:

```text
FragmentationModel
VibrationModel
OversizeModel
ToeRiskModel
```

---

# PHASE BDX-014 — Uncertainty and Model Applicability

## Goal

Prevent ML from presenting false precision.

Every prediction must return:

```text
prediction
uncertainty
confidence
similarity_score
applicability_warning
```

Example UI:

```text
Predicted X50:
312 mm

Expected interval:
270–365 mm

Confidence:
Medium

Comparable historical blasts:
47

Similarity:
82 %
```

Detect extrapolation.

Example:

```text
Historical diameter range:
152–229 mm

Requested:
311 mm

WARNING:
Prediction is outside the calibrated domain.
```

ML predictions outside the training domain must be visibly flagged.

---

# PHASE BDX-015 — Explainability

## Goal

Explain why BlastEX predicts or recommends something.

Support feature importance and SHAP-style explanations.

Example:

```text
Main X50 drivers:

Burden          28 %
Powder Factor   24 %
UCS              17 %
Spacing          12 %
Stemming          8 %
Timing            6 %
Other             5 %
```

Recommendation explanation example:

```text
Reducing burden:
expected X50 -34 mm

Increasing PF:
expected oversize -1.4 %

Increasing row delay:
expected PPV -0.8 mm/s

Changing ANFO to emulsion:
expected direct cost +4.2 %
```

The engineer must be able to understand why a design was recommended.

---

# PHASE BDX-016 — Scenario Engine

## Goal

Compare engineering alternatives without modifying the approved design.

Example:

```text
Scenario A
165 mm
5.0 × 6.0 m
q = 0.65

Scenario B
165 mm
5.5 × 6.5 m
q = 0.58
```

Compare:

```text
drilling metres
explosive mass
X50
X80
oversize
MIC
PPV
direct cost
total predicted cost
```

---

# PHASE BDX-017 — Multi-Objective Optimisation

## Goal

Generate rational design alternatives.

Variables may include:

```text
diameter
burden
spacing
subdrill
stemming
explosive
charge concentration
decking
hole inclination
inter-hole delay
inter-row delay
```

Objectives:

```text
minimise total cost
minimise oversize
minimise drilling
minimise PPV
target X50
```

Constraints:

```text
minimum burden
minimum stemming
maximum PF
maximum PPV
target fragmentation range
available explosive products
drill-rig constraints
```

Initially use deterministic parameter sweeps and Pareto optimisation.

Do not introduce reinforcement learning.

---

# PHASE BDX-018 — ML Design Recommendation Engine

## Goal

Use historical mine knowledge to recommend future blast alternatives.

Workflow:

```text
New Blast Block
      ↓
Geology / Geometry
      ↓
Candidate Generator
      ↓
Engineering Constraints
      ↓
Engineering Models
      ↓
Mine-Specific ML Models
      ↓
Cost Engine
      ↓
Pareto Optimiser
      ↓
Top Recommended Designs
```

Return multiple alternatives.

Example:

```text
BALANCED
LOW COST
FINE FRAGMENTATION
LOW VIBRATION
```

Each recommendation must contain:

```text
design parameters
predicted outcomes
uncertainty
estimated cost
constraints satisfied
historical similarity
explanation
```

BlastEX must never automatically approve the recommended design.

---

# PHASE BDX-019 — Global and Site-Specific Learning

## Goal

Support new mines with limited historical data.

Architecture:

```text
Global Model
      +
Mine-Specific Calibration
      ↓
Site Model
```

Possible strategy:

```text
Global model trained on multiple authorised datasets
        ↓
site-specific residual model
```

Data isolation is mandatory.

Introduce explicit policies:

```text
private_site_data
shared_anonymised_data
global_model_opt_in
```

Default:

```text
private_site_data = true
global_model_opt_in = false
```

Never mix customer data automatically.

---

# PHASE BDX-020 — Model Registry and ML Lifecycle

## Goal

Make ML reproducible and auditable.

Create a model registry.

Each model version stores:

```text
model_id
site_id
model_type
version
dataset_version
feature_schema_version
algorithm
hyperparameters
metrics
created_at
status
```

Statuses:

```text
candidate
validated
production
superseded
rejected
```

Production predictions must always identify the exact model version.

---

# PHASE BDX-021 — Model Validation and Drift

## Goal

Detect when historical ML becomes unreliable.

Track:

```text
prediction error
feature drift
target drift
model degradation
out-of-domain usage
```

Example:

```text
Fragmentation model v7

Training X50 MAE:
41 mm

Last 10 blasts:
73 mm

Status:
DEGRADED
```

Do not automatically retrain and deploy.

Require a controlled validation workflow.

---

# PHASE BDX-022 — Hole-Level and Spatial ML

## Goal

Progress from blast-level prediction to local spatial prediction.

Represent each hole or influence region as:

```python
HoleFeatureVector
```

Features may include:

```text
local geology
local burden
local spacing
local PF
stemming
charge concentration
timing
distance to face
neighbour timing
water
```

Potential targets:

```text
local fragmentation
local movement
toe probability
backbreak risk
```

This phase becomes useful once sufficiently detailed spatial post-blast measurements exist.

---

# PHASE BDX-023 — Blast Movement / Heave Model

## Goal

Develop an engineering movement approximation.

Calculate:

```text
available relief
relief direction
time since neighbouring firing
local burden
charge energy
```

Produce:

```text
movement vectors
predicted throw direction
muckpile envelope
crest movement
toe movement
```

Outputs must be explicitly identified as engineering estimates.

Do not imitate high-fidelity numerical physics without validated models.

---

# PHASE BDX-024 — Reporting and Blast Passport

## Goal

Produce a complete engineering record.

Report sections:

```text
General information
Input data
Survey data
Geology
Blast geometry
Hole schedule
Charging
Initiation
Timing
Fragmentation prediction
Vibration prediction
ML predictions
Model confidence
Engineering warnings
Cost
Execution data
Post-blast results
Prediction vs measured
Revision history
```

Export roadmap:

```text
CSV
PDF
DXF
XLSX
GeoJSON
JSON
```

---

# PHASE BDX-025 — Persistence and Lifecycle

## Goal

Support production engineering history.

Introduce revisioning.

Lifecycle:

```text
Draft
Calculated
Checked
Approved
Issued for Drilling
As Drilled
Issued for Charging
As Charged
Fired
Closed
```

Approved versions must never be silently overwritten.

Move to PostgreSQL when revision history, ML datasets and post-blast measurements make JSON persistence insufficient.

Use repository interfaces so domain calculations remain storage-independent.

---

# PHASE BDX-026 — Engineering Workstation UI

## Goal

Transform the current design interface into a full blast-engineering workstation.

Recommended layout:

```text
┌──────────────────────────────────────────────────────────────┐
│ Mine / Bench / Blast / Revision / Status                    │
├──────────────┬───────────────────────────────┬───────────────┤
│ Design Tree  │                               │ Properties    │
│              │           Canvas              │               │
│ Terrain      │      Plan / Section / 3D      │ Hole          │
│ Geology      │                               │ Charge        │
│ Pattern      │                               │ Timing        │
│ Charging     │                               │ Prediction    │
│ Timing       │                               │ ML            │
├──────────────┴───────────────────────────────┴───────────────┤
│ Analysis / Warnings / Scenarios / History / ML              │
└──────────────────────────────────────────────────────────────┘
```

Layers:

```text
terrain
floor
geology
blast contour
holes
toes
hole tracks
charges
timing
burden
spacing
PF
fragmentation
vibration
warnings
as-drilled
as-charged
movement
```

---

# 27. Undo / Redo and Editing Infrastructure

Introduce command-based editing before the editor becomes significantly more complex.

Commands must support:

```text
move hole
add hole
delete hole
change depth
edit charge
apply charge rule
create connector
change timing
modify contour
```

---

# 28. Engineering Provenance

Every calculated or predicted result must store:

```text
model name
model version
parameters
inputs
design revision
timestamp
```

Every measurement must store:

```text
source
measurement method
timestamp
confidence
operator/import source
```

---

# 29. Unit Discipline

Define canonical units.

Recommended:

```text
distance        m
diameter        mm
mass            kg
time            ms
velocity        m/s
PPV             mm/s
density         explicit SI representation
pressure        MPa / Pa with controlled conversion
```

Do not allow silent density or unit conversions.

---

# 30. Validation Severity

Replace flat warnings with:

```text
info
warning
error
blocking
```

Example:

```python
EngineeringIssue(
    code="MIN_FACE_BURDEN",
    severity="error",
    entity_type="hole",
    entity_id="3-07",
    measured_value=2.1,
    limit_value=3.0,
)
```

Separate:

```text
engineering heuristic
company rule
user constraint
regulatory rule
```

Do not claim regulatory compliance unless jurisdiction and rule source are explicitly configured.

---

# Recommended Implementation Sequence

Execute approximately in this order:

```text
BDX-001  Spatial Foundation
BDX-002  Geological Domains
BDX-003  Advanced Pattern Design
BDX-004  Charging Rules Engine
BDX-005  Initiation Network 2.0
BDX-006  Fragmentation Simulation
BDX-007  Vibration and Receptors
BDX-008  As-Drilled
BDX-009  As-Charged / As-Fired
BDX-010  Post-Blast Measurements
BDX-011  ML Data Foundation
BDX-012  Site Calibration ML
BDX-013  Outcome Prediction
BDX-014  Uncertainty
BDX-015  Explainability
BDX-016  Scenario Engine
BDX-017  Multi-Objective Optimisation
BDX-018  ML Recommendation Engine
BDX-019  Global + Site Learning
BDX-020  Model Registry
BDX-021  Drift Monitoring
BDX-022  Spatial ML
BDX-023  Movement / Heave
BDX-024  Reporting
BDX-025  Persistence / Lifecycle
BDX-026  Engineering Workstation Hardening
```

Some persistence, UI and provenance work must be implemented incrementally throughout earlier tasks.

---

# First Major Milestone

## BlastEX Design 1.0

Must support:

```text
real terrain
blast contour
advanced pattern
geological domains
charging rules
editable initiation
timing analysis
fragmentation prediction
vibration prediction
cost
engineering passport
```

---

# Second Major Milestone

## BlastEX Execution 1.0

Must support:

```text
as-drilled
as-charged
as-fired
post-blast measurements
design vs actual
predicted vs measured
```

---

# Third Major Milestone

## BlastEX Intelligence 1.0

Must support:

```text
site datasets
site calibration
fragmentation ML
vibration ML
uncertainty
explainability
scenario comparison
design recommendations
```

Recommendation output must resemble:

```text
Option A — Balanced
Option B — Lowest Cost
Option C — Fine Fragmentation
Option D — Low Vibration
```

rather than one unexplained “optimal” result.

---

# Final Product Principle

BlastEX should always be able to answer:

```text
WHAT DID WE DESIGN?

WHAT DID WE ACTUALLY EXECUTE?

WHAT DID WE PREDICT?

WHAT ACTUALLY HAPPENED?

WHAT DID THE SYSTEM LEARN?

WHAT SHOULD WE TRY NEXT?
```

The main competitive advantage should not be CAD alone.

The differentiator should be the closed engineering-learning loop:

```text
DESIGN
   ↓
SIMULATE
   ↓
RECOMMEND
   ↓
ENGINEER APPROVES
   ↓
EXECUTE
   ↓
MEASURE
   ↓
CALIBRATE
   ↓
LEARN
   ↓
OPTIMISE
```

---

# РУССКАЯ ВЕРСИЯ

## Цель

Развить BlastEX из приложения для расчёта параметров БВР и базового проектирования в полноценную инженерную платформу:

```text
ПРОЕКТИРОВАНИЕ
      ↓
ПРОГНОЗ
      ↓
ОПТИМИЗАЦИЯ
      ↓
ИСПОЛНЕНИЕ
      ↓
ИЗМЕРЕНИЕ РЕЗУЛЬТАТА
      ↓
ОБУЧЕНИЕ
      ↓
РЕКОМЕНДАЦИИ
```

BlastEX должен объединять:

- проектирование БВР;
- пространственную модель уступа;
- геологическую модель;
- проектирование зарядов;
- проектирование инициирования;
- прогноз дробления;
- прогноз сейсмического воздействия;
- приближённое моделирование перемещения массива;
- экономику БВР;
- фактическое исполнение;
- измерение результатов взрыва;
- ML-калибровку моделей;
- прогнозирование для конкретного месторождения;
- многокритериальный подбор вариантов.

Долгосрочная цель:

> **BlastEX должен обучаться на каждом выполненном взрыве и использовать историю конкретного месторождения для предложения более безопасных, дешёвых и предсказуемых вариантов БВР.**

ML является системой поддержки инженерных решений.

Он не должен самостоятельно изменять или утверждать проект.

---

# 1. Основная архитектура

Целевой процесс:

```text
Месторождение
      ↓
Уступ / Геология
      ↓
Проект БВР
      ↓
Физические и эмпирические модели
      ↓
Коррекция прогноза через ML
      ↓
Сравнение сценариев
      ↓
Выбор инженером
      ↓
Факт бурения
      ↓
Факт зарядки
      ↓
Факт инициирования
      ↓
Измерение результата
      ↓
Обучающая выборка
      ↓
Модель месторождения
      ↓
Рекомендации для следующего взрыва
```

Необходимо строго разделять:

```text
ЗАПРОЕКТИРОВАНО
ФАКТИЧЕСКИ ВЫПОЛНЕНО
СПРОГНОЗИРОВАНО
ИЗМЕРЕНО
```

Проектные данные нельзя заменять фактическими.

---

# 2. Модель месторождения

Добавить сущность:

```text
MineSite / Месторождение
```

Она должна включать:

```text
систему координат
уступы
геологические зоны
проекты взрывов
фактические результаты
наборы данных для обучения
реестр ML-моделей
```

ML-модели должны принадлежать конкретному месторождению.

---

# 3. Стратегия ML

Необходимо использовать гибридный подход:

```text
Инженерная модель
        +
История взрывов
        +
ML
        ↓
Прогноз результата
        ↓
Оптимизация
        ↓
Рекомендованные варианты
```

Предпочтительная схема:

```text
Классический расчёт
       ↓
ML-коррекция
       ↓
Прогноз, откалиброванный по месторождению
```

Например:

```text
Kuz-Ram:
X50 = 380 мм

ML-коррекция:
-52 мм

Итоговый прогноз BlastEX:
X50 = 328 мм
```

---

# 4. Уровни развития ML

## Уровень 0 — Сбор данных

ML ещё ничего не прогнозирует.

BlastEX лишь гарантирует, что каждый закрытый взрыв превращается в качественный набор данных.

Этот фундамент нужно закладывать сразу.

---

## Уровень 1 — Калибровка моделей

ML корректирует классические инженерные модели.

Например:

```text
Kuz-Ram → фактическая калибровка X50
PPV-модель → калибровка по данным сейсмостанций
```

Это первая ML-функция, которую стоит выводить в production.

---

## Уровень 2 — Прогноз результата

ML напрямую прогнозирует:

```text
X20
X50
X80
негабарит
PPV
частоту колебаний
вероятность порогов
backbreak
вторичное дробление
характеристики развала
```

---

## Уровень 3 — Рекомендации

BlastEX формирует множество допустимых вариантов БВР.

ML прогнозирует результат каждого варианта.

Оптимизатор выбирает лучшие варианты по заданным критериям.

---

# BDX-001 — Пространственная модель уступа

Создать полноценную модель:

```text
SurfaceModel
TIN
TopSurface
FloorSurface
FaceSurface
PostBlastSurface
```

Импорт:

```text
XYZ
CSV
DXF
GeoJSON
```

Устья скважин должны получать фактическую отметку поверхности.

Глубина должна уметь рассчитываться относительно поверхности подошвы.

---

# BDX-002 — Геологические зоны

Добавить:

```text
BlastDomain
HoleInterval
WaterInterval
RockPropertySet
```

Поддержать:

```text
плотность
UCS
трещиноватость
RQD
модуль Юнга
коэффициент Пуассона
скорость продольной волны
ориентацию трещин
blastability
обводнённость
```

---

# BDX-003 — Продвинутая сетка скважин

Поддержать:

```text
регулярную сетку
шахматную
переменную
геологически зависимую
```

Типы скважин:

```text
production
buffer
trim
presplit
contour
stab
satellite
infill
```

Добавить:

```text
реальную ЛНС
ЛНС первого ряда
ЛНС по забою
ЛНС по устью
локальный шаг
ручную корректировку скважин
```

---

# BDX-004 — Rule Engine зарядки

Заряжание должно зависеть от:

```text
типа скважины
ряда
геологии
обводнённости
глубины
ЛНС
шага
диаметра
целевого удельного расхода
```

Поддержать:

```text
несколько типов ВВ в одной скважине
воздушные промежутки
инертные промежутки
боевики
промежуточные детонаторы
несколько инициаторов
```

---

# BDX-005 — Инициирование 2.0

Создать редактируемую сеть инициирования.

Поддержать:

```text
NONEL
ДШ
электронные детонаторы
```

Назначение времени:

```text
по рядам
по выборке
по направлению
по формуле
по каждой скважине
по каждой деке
по каждому боевику
```

Добавить анализ ошибок и MIC.

---

# BDX-006 — Прогноз дробления

Создать отдельный пакет моделирования.

Поддержать:

```text
Кузнецов
Kuz-Ram
Swebrec
```

Считать:

```text
X20
X50
X80
негабарит
грансостав
```

в том числе локально по блоку.

---

# BDX-007 — Сейсмика и рецепторы

Добавить точки контроля:

```text
здания
трубопроводы
ЛЭП
дробилки
борта
сейсмостанции
```

Для каждой рассчитывать PPV.

Сохранять реальные измерения для последующей ML-калибровки.

---

# BDX-008 — Фактическое бурение

Хранить:

```text
проектное устье
фактическое устье
проектный забой
фактический забой
глубину
азимут
угол
траекторию
```

Считать фактическую геометрию сетки.

---

# BDX-009 — Фактическая зарядка и инициирование

Хранить:

```text
фактические массы ВВ
фактические деки
забойку
положение боевиков
детонаторы
программные времена
фактическое состояние сети
```

---

# BDX-010 — Результаты взрыва

Хранить:

```text
X20
X50
X80
негабарит
PPV
частоты
заколы
пороги
развал
вторичное дробление
фактические затраты
```

Сравнивать:

```text
проект ↔ факт
прогноз ↔ измерение
плановая стоимость ↔ фактическая
```

---

# BDX-011 — ML Data Foundation

Создать:

```text
intelligence/
    datasets/
```

Каждый закрытый взрыв должен формировать неизменяемый snapshot обучающего набора.

Группы признаков:

```text
месторождение
геология
геометрия
заряжание
инициирование
фактическое исполнение
условия
```

Целевые показатели:

```text
дробление
сейсмика
качество взрыва
экономика
```

---

# BDX-012 — ML-калибровка месторождения

Первая производственная ML-функция.

ML корректирует:

```text
X50
негабарит
PPV
```

по истории конкретного месторождения.

Базовые алгоритмы:

```text
CatBoost
XGBoost
LightGBM
Random Forest
Extra Trees
```

Нейронные сети не использовать без достаточного объёма данных.

---

# BDX-013 — Прямой ML-прогноз

Создать специализированные модели:

```text
FragmentationModel
VibrationModel
OversizeModel
ToeRiskModel
```

Не пытаться сразу сделать одну универсальную нейросеть.

---

# BDX-014 — Неопределённость

Каждый ML-прогноз должен содержать:

```text
значение
интервал
confidence
similarity
признак экстраполяции
```

Пример:

```text
X50:
312 мм

Ожидаемый диапазон:
270–365 мм

Уверенность:
Средняя

Похожих взрывов:
47
```

---

# BDX-015 — Объяснимость ML

Инженер должен видеть, почему модель дала прогноз.

Например:

```text
Основные факторы X50:

ЛНС             28%
Удельный расход 24%
UCS              17%
Шаг              12%
Забойка           8%
Замедления        6%
```

---

# BDX-016 — Сценарии

Позволить создавать несколько альтернатив одного блока:

```text
Вариант A
Вариант B
Вариант C
```

и сравнивать по:

```text
бурению
ВВ
X50
негабариту
MIC
PPV
стоимости
```

---

# BDX-017 — Многокритериальная оптимизация

Оптимизировать:

```text
стоимость
дробление
негабарит
PPV
объём бурения
```

при инженерных ограничениях.

На первом этапе использовать перебор параметров и Pareto frontier.

---

# BDX-018 — ML-рекомендации

Для нового блока:

```text
геология + геометрия
       ↓
генерация вариантов
       ↓
инженерные ограничения
       ↓
классические модели
       ↓
ML месторождения
       ↓
смета
       ↓
оптимизатор
       ↓
лучшие варианты
```

Показывать, например:

```text
Сбалансированный
Минимальная стоимость
Тонкое дробление
Минимальная сейсмика
```

---

# BDX-019 — Global Model + Site Model

Для новых месторождений предусмотреть:

```text
Общая модель
     +
Локальная калибровка
     ↓
Модель месторождения
```

При этом данные заказчиков не смешивать автоматически.

По умолчанию:

```text
private_site_data = true
global_model_opt_in = false
```

---

# BDX-020 — Реестр моделей

Для каждой ML-модели сохранять:

```text
месторождение
тип
версию
dataset
feature schema
алгоритм
гиперпараметры
метрики
статус
```

Статусы:

```text
candidate
validated
production
superseded
rejected
```

---

# BDX-021 — Drift Monitoring

Отслеживать ухудшение модели.

Например:

```text
MAE при обучении:
41 мм

MAE последних 10 взрывов:
73 мм

Статус:
DEGRADED
```

Переобучение не должно автоматически попадать в production.

---

# BDX-022 — Пространственный ML

В будущем перейти от уровня блока к уровню скважины.

Для каждой скважины формировать:

```text
HoleFeatureVector
```

с локальными:

```text
геологией
ЛНС
шагом
зарядом
забойкой
замедлением
соседними скважинами
расстоянием до откоса
```

---

# BDX-023 — Развал и перемещение массива

Рассчитывать приближённые:

```text
вектор перемещения
направление развала
ширину развала
перемещение бровки
перемещение подошвы
```

Не выдавать эмпирическую модель за высокоточную физику.

---

# BDX-024 — Паспорт и отчётность

Паспорт должен включать:

```text
исходные данные
геометрию
геологию
сетку
зарядку
инициирование
дробление
сейсмику
ML-прогноз
неопределённость
замечания
стоимость
факт
результаты
прогноз vs факт
историю версий
```

---

# BDX-025 — Жизненный цикл и БД

Жизненный цикл:

```text
Draft
Calculated
Checked
Approved
Issued for Drilling
As Drilled
Issued for Charging
As Charged
Fired
Closed
```

При росте данных перейти с JSON на PostgreSQL.

Но расчётное ядро не должно зависеть от конкретной БД.

---

# BDX-026 — Инженерное рабочее место

Итоговый интерфейс:

```text
┌────────────────────────────────────────────────────────────┐
│ Месторождение / Уступ / Блок / Ревизия / Статус           │
├──────────────┬──────────────────────────────┬──────────────┤
│ Дерево       │                              │ Свойства     │
│ проекта      │       План / Разрез / 3D     │              │
│              │                              │ Скважина     │
│ Поверхности  │                              │ Заряд        │
│ Геология     │                              │ Инициирование│
│ Сетка        │                              │ ML           │
├──────────────┴──────────────────────────────┴──────────────┤
│ Анализ / Ошибки / Сценарии / История / ML                 │
└────────────────────────────────────────────────────────────┘
```

---

# Основные этапы продукта

## BlastEX Design 1.0

```text
реальный уступ
геология
профессиональная сетка
зарядка
инициирование
дробление
сейсмика
смета
паспорт
```

## BlastEX Execution 1.0

```text
факт бурения
факт зарядки
факт инициирования
результаты
проект vs факт
прогноз vs факт
```

## BlastEX Intelligence 1.0

```text
обучающие datasets
модель месторождения
ML-калибровка
прямой прогноз
uncertainty
explainability
сценарии
ML-рекомендации
```

---

# Главный принцип BlastEX

Система должна всегда отвечать на шесть вопросов:

```text
ЧТО МЫ ЗАПРОЕКТИРОВАЛИ?

ЧТО МЫ ФАКТИЧЕСКИ ВЫПОЛНИЛИ?

ЧТО МЫ ПРОГНОЗИРОВАЛИ?

ЧТО ФАКТИЧЕСКИ ПОЛУЧИЛИ?

ЧЕМУ СИСТЕМА НАУЧИЛАСЬ?

ЧТО СТОИТ ПОПРОБОВАТЬ В СЛЕДУЮЩИЙ РАЗ?
```

Целевой цикл:

```text
ПРОЕКТ
   ↓
МОДЕЛИРОВАНИЕ
   ↓
РЕКОМЕНДАЦИИ
   ↓
РЕШЕНИЕ ИНЖЕНЕРА
   ↓
ИСПОЛНЕНИЕ
   ↓
ИЗМЕРЕНИЕ
   ↓
КАЛИБРОВКА
   ↓
ОБУЧЕНИЕ
   ↓
ОПТИМИЗАЦИЯ
```

Именно этот замкнутый цикл должен стать главным отличием BlastEX от обычного CAD для БВР.
