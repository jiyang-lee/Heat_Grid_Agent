# PreDist Dataset: Operational data of district heating substations labelled with faults and maintenance actions

This dataset consists of operational data and labels based on incident reports of district heating substations
of enercity AG. The labels are available as a list of ‘disturbances’ as well as a list of fault reports 
including a short description and problem category, which can be used to develop (early) fault detection models
for district heating substations. In addition, fault labels and monitoring potential were added to the reports
where possible. 

This dataset is published on Zenodo [10.5281/zenodo.17522255](doi.org/10.5281/zenodo.17522255).

## Dataset

This data contains time series of 93 district heating substations from two manufacturers, M1 and M2, each time
series spanning different lengths of time, depending on when the substation was ‘digitised’. Both sub-datasets
contain a list of faults (based on incident reports), a list of disturbances (faults, and corrective and 
preventive maintenance tasks and activities), feature descriptions and a list of pre-defined ‘normal events’,
which can be used in addition to the faults to evaluate normal behaviour models.

Note that incident reports or disturbances do not exist for all substations. This does not necessarily mean the
substation only exhibits normal behaviour; faults may still be present. These faults did not lead to a decrease
in comfort, so the customer did not report a problem.

The file structure is as follows:
- Manufacturer `<x>`
  - operational_data
    - substation_<id>.csv
    - ...
    - <substation_id>.csv
  - [disturbances.csv](#Disturbances)
  - [faults.csv](#faultscsv)
  - [normal_events.csv](#normal_eventscsv)
  - [feature_descriptions.csv](#feature-description)

### faults.csv
This file is based on the incident reports made by customers. It only contains reports where a fault in the 
substation was found.

Columns:
- ‘substation ID’
- ‘Report date’: Report date, when the customer reported a problem
- ‘Problem EN’: problem category, i.e., no heat, no DHW, etc.
- ‘Event description EN’: Description of the problem, underlying cause if known and solution if known.
- ‘Possible anomaly start’: If an anomaly was visible in the data, we marked it here. This can be used for normal behaviour selection.
- ‘Possible anomaly end’: The following maintenance task plus 4 hours. If no tasks follow this report, this is empty. This can be used for normal behaviour selection.
- ‘Training start’ / ‘Training end’: The training data we used to try to detect the fault, and we recommend to use.
- ‘efd_possible’: Whether early fault detection might be possible and is useful for this event. For example, if there is no training data, or when the event was reported before, this is set to False.
- ‘Fault label’: fault label (see table A.5 in [this paper](https://doi.org/10.1016/j.energy.2025.137210))
- ‘Monitoring potential’: Monitoring potential (see table A.5 in [this paper](https://doi.org/10.1016/j.energy.2025.137210))
   Indicates how detectable a fault is. A low monitoring potential means the fault is not detectable, or only with extra sensor measurements. Faults that are detectable before the failure have a higher monitoring potential than faults that are only detectable after a failure. 

### normal_events.csv
Predefined normal behaviour examples, to evaluate a normal behaviour model’s ability to recognise normal 
behaviour correctly.

Columns:
- ‘substation ID’
- ‘Event start’ / ‘Event end’: Test data, from when to when we expect the data to represent normal behaviour. A fault detection model should not detect faults or anomalies here.
- ‘Training start’ / ‘Training end’: Training data we used and recommend

### Disturbances
Lists maintenance activities and incident reports.

Columns:
- ‘substation ID’
- ‘Event start’: When maintenance activity started or when incident report was made
- ‘type’: type of disturbance. Incident reports are labelled ‘fault’, maintenance activities ‘task’ or ‘activity’.

‘Tasks’ refer to maintenance actions only, whereas ‘activities’ may also include incident reports. This 
distinction results from a change in the operator’s data management: previously, both incident reports and 
maintenance tasks were tracked in a single ‘activities’ table. Disturbances can be used to select time ranges
without faults or maintenance interventions that represent expected normal behaviour.

### Feature description
In the `feature_descriptions.csv` file you will find a short description (M1) and the measurement unit of the 
features in the operational datasets. Note that not all datasets have the same features; for some only a subset
is available, due to the different configurations of the substations.

The column names have been standardized for both datasets. The names are structured as follows:
- Primary or secondary side, indicated by 'p' or 's'
- Heat circuit or DHW, indicated as, for example, hc1, hc1.1, dhw
- Place, indicated as 'supply', 'return', 'upper', 'lower'', 'room'
- Component, e.g., control unit, storage, circulation pump
- Dimension, e.g. temperature, status, flow, power
- Metric type, e.g. setpoint, mode (measurement if not specified) 

For example: `p_hc1_return_temperature` is the primary side return temperature of heat circuit 1 and
`p_hc1_return_temperature_setpoint` is the setpoint for this measurement.

## Anomalies, known data gaps and other useful information
Since this dataset contains real-world data labelled with service reports, the datasets can contain anomalies 
that change the distribution of the data, which are not directly connected to service reports. These anomalies
can be caused by changing customer behaviour or control parameters of the substation, and may even be faults 
that did not reduce comfort levels, so no incident report was made.

The first month of each time series should often be removed, as this part can contain strange behaviour due to
commissioning issues or maintenance activities (for example, frequently changing control parameters).

Some of the datasets contain large data gaps, ranging from a day to (in one case) a couple of years. Other 
datasets lack data from either the controller or the meter for a period of time. We did not remove time series
where part of the data (for example, the meter data) was missing, since the remaining time series can still be
useful.

Also, in some cases the outside temperature is not available or has implausible values, for example, for 
substations 18, 41 and 61 of the Manufacturer 2 dataset. Usually this means that the substation is only used
for DHW. In other cases the controller simply does not use the outside temperature and only uses the set 
points for the flow and room temperatures.

The following ‘anomalies’ over 24 h in the datasets, that are not labelled by the reports, are known, and 
should probably be accounted for when creating data-driven models. This is not an exhaustive list.

| Manufacturer | substation ID | From       | To         | Description                                                                              |
|--------------|---------------|------------|------------|------------------------------------------------------------------------------------------|
| 1            | 1             | start      | 2018-07-20 | Change in behaviour                                                                      |
| 1            | 19            | start      | 2016-06    | Broken outside temperature sensor                                                        |
| 1            | 21            | 2019-10    | end        | HC1 flow temperature and its reference/set point more or less constant                   |
| 1            | 33            | 2018-10    | 2018-11    | No DHW, both storage temperatures low                                                    |
| 1            | 33            | 2020-03-01 | 2020-03-31 | No DHW, both storage temperatures low                                                    |
| 2            | 22            | 2019-09-16 | 2019-09-25 | No flow                                                                                  |
| 2            | 22            | 2020-02-11 | 2020-03-17 | No flow                                                                                  |
| 2            | 41            | 2017-04    | 2017-12    | No DHW, both storage temperatures low                                                    |
| 2            | 34            | 2017-09    | end        | No DHW, both storage temperatures low                                                    |

