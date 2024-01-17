# Mapping of Data Elements to FHIR Resources - Documentation

## Introduction

This documentation provides a detailed mapping of data elements from an MIP JSON structure to the corresponding Fast Healthcare Interoperability Resources (FHIR) format. The MIP JSON structure contains information related to traumatic brain injury (TBI) assessment, including demographic data, Glasgow Coma Scale (GCS) scores, imaging assessment, and laboratory tests. The goal is to demonstrate how each data element can be mapped to FHIR resources for improved interoperability and healthcare data exchange.

## Table of Contents

1. [Patient Demographics](#1-patient-demographics)
2. [Neurological Assessment](#2-neurological-assessment)
3. [Imaging Assessment](#3-imaging-assessment)
4. [Systemic Second Insult](#4-systemic-second-insult)

---

### 1. Patient Demographics

**Original JSON Structure:**
```json
{
      "variables": [
        {
            "isCategorical": false,
            "label": "subjectcode",
            "code": "subjectcode",
            "sql_type": "text",
            "description": "",
            "methodology": "",
            "type": "nominal"
        },
        {
          "isCategorical": false,
          "minValue": 0,
          "code": "age_value",
          "maxValue": 130,
          "sql_type": "int",
          "description": "",
          "label": "Age",
          "units": "years",
          "type": "integer",
          "methodology": ""
        },
        {
          "isCategorical": true,
          "code": "gender_type",
          "sql_type": "text",
          "description": "",
          "enumerations": [
            {
              "code": "M",
              "label": "Male"
            },
            {
              "code": "F",
              "label": "Female"
            }
          ],
          "label": "Gender",
          "units": "",
          "type": "nominal",
          "methodology": ""
        }
      ],
      "code": "Demographics",
      "label": "Demographics"
    }
```
- Contains variables for "subjectcode" (identifier), "age_value" (age), and "gender_type" (gender).
- Gender is represented as "M" (Male) or "F" (Female).

**Mapped FHIR Resource:**
```json
{
  "resourceType": "Patient",
  "id": "patient-example",
  "identifier": [
    { "use": "usual", "value": "subjectcode" }
  ],
  "age": "age_value",
  "gender": "gender_type"
}
```
- Uses the FHIR `Patient` resource.
- Maps the "subjectcode" to the patient's identifier.
- Maps "age_value" to the patient's age.
- Maps "gender_type" to the patient's gender.

---

### 2. Neurological Assessment

**Original JSON Structure:**
```json
{
      "variables": [
        {
          "isCategorical": true,
          "code": "pupil_reactivity_right_eye_result",
          "sql_type": "text",
          "description": "Pupil reactivity light right eye",
          "enumerations": [
            {
              "code": "Sluggish",
              "label": "Sluggish"
            },
            {
              "code": "Nonreactive",
              "label": "Nonreactive"
            },
            {
              "code": "Brisk",
              "label": "Brisk"
            },
            {
              "code": "Untestable",
              "label": "Untestable"
            },
            {
              "code": "Unknown",
              "label": "Unknown"
            }
          ],
          "label": "Pupil right",
          "units": "",
          "type": "nominal",
          "methodology": ""
        },
        {
          "isCategorical": true,
          "code": "pupil_reactivity_left_eye_result",
          "sql_type": "text",
          "description": "Pupil reactivity light left eye ",
          "enumerations": [
            {
              "code": "Sluggish",
              "label": "Sluggish"
            },
            {
              "code": "Nonreactive",
              "label": "Nonreactive"
            },
            {
              "code": "Brisk",
              "label": "Brisk"
            },
            {
              "code": "Untestable",
              "label": "Untestable"
            },
            {
              "code": "Unknown",
              "label": "Unknown"
            }
          ],
          "label": "Pupil left",
          "units": "",
          "type": "nominal",
          "methodology": ""
        },
        {
          "isCategorical": true,
          "code": "gcs_total_score",
          "sql_type": "text",
          "description": "Glasgow Coma Scale (GCS) - total score",
          "enumerations": [
            {
              "code": "3",
              "label": "3"
            },
            {
              "code": "4",
              "label": "4"
            },
            {
              "code": "5",
              "label": "5"
            },
            {
              "code": "6",
              "label": "6"
            },
            {
              "code": "7",
              "label": "7"
            },
            {
              "code": "8",
              "label": "8"
            },
            {
              "code": "9",
              "label": "9"
            },
            {
              "code": "10",
              "label": "10"
            },
            {
              "code": "11",
              "label": "11"
            },
            {
              "code": "12",
              "label": "12"
            },
            {
              "code": "13",
              "label": "13"
            },
            {
              "code": "14",
              "label": "14"
            },
            {
              "code": "15",
              "label": "15"
            },
            {
              "code": "untestable",
              "label": "untestable"
            },
            {
              "code": "unknown",
              "label": "unknown"
            }
          ],
          "label": "GSC total",
          "units": "",
          "type": "nominal",
          "methodology": ""
        }
      ],
      "code": "Neurological Assessment",
      "label": "Neurological Assessment"
}
```
- Contains variables for pupil reactivity of the right and left eye ("pupil_reactivity_right_eye_result" and "pupil_reactivity_left_eye_result") and Glasgow Coma Scale total score ("gcs_total_score").
- Uses text values to represent pupil reactivity and GCS total score.

**Mapped FHIR Resource:**
```json
{
  "resourceType": "Observation",
  "id": "neuro-assessment-example",
  "code": {
    "coding": [
      { "system": "http://loinc.org", "code": "GCS code", "display": "Glasgow Coma Scale Total Score" }
    ]
  },
  "subject": { "reference": "Patient/patient-example" },
  "component": [
    {
      "code": { "coding": [{ "system": "http://loinc.org", "code": "gcs_total_score", "display": "GCS Total Score" }] },
      "valueQuantity": { "value": "score value" }
    },
    {
      "code": { "coding": [{ "system": "http://loinc.org", "code": "pupil_reactivity_right_eye_result", "display": "Pupil Reactivity Right Eye" }] },
      "valueString": "reactivity description"
    },
    {
      "code": { "coding": [{ "system": "http://loinc.org", "code": "pupil_reactivity_left_eye_result", "display": "Pupil Reactivity Left Eye" }] },
      "valueString": "reactivity description"
    }
  ]
}
```
- Uses the FHIR `Observation` resource.
- Maps pupil reactivity and GCS total score to components within the observation.
- Uses LOINC codes for standardized representation.
- Uses text values to represent pupil reactivity.

---

### 3. Imaging Assessment

**Original JSON Structure:**
```json
{
      "variables": [
        {
          "isCategorical": true,
          "code": "cisternal_compression_status",
          "sql_type": "text",
          "description": "Cisternal compression status",
          "enumerations": [
            {
              "code": "Present",
              "label": "Present"
            },
            {
              "code": "Absent",
              "label": "Absent"
            },
            {
              "code": "Indeterminate",
              "label": "Indeterminate"
            }
          ],
          "label": "Cisternal compression",
          "units": "",
          "type": "nominal",
          "methodology": ""
        }
      ],
      "code": "Imaging Assessment",
      "label": "Imaging Assessment"
    }
```
- Contains a variable for "cisternal_compression_status."
- Uses text values "Present," "Absent," or "Indeterminate" to represent cisternal compression status.

**Mapped FHIR Resource:**
```json
{
  "resourceType": "Observation",
  "id": "imaging-assessment-example",
  "code": {
    "coding": [
      { "system": "http://loinc.org", "code": "Imaging code", "display": "Imaging Assessment" }
    ]
  },
  "subject": { "reference": "Patient/patient-example" },
  "component": [
    {
      "code": { "coding": [{ "system": "http://loinc.org", "code": "cisternal_compression_status", "display": "Cisternal Compression" }] },
      "valueString": "Present/Absent/Indeterminate"
    }]
}
```
- Uses the FHIR `Observation` resource.
- Maps "cisternal_compression_status" to a component within the observation.
- Uses LOINC codes for standardized representation.
- Uses text values to represent cisternal compression status.

---

### 4. Systemic Second Insult

**Original JSON Structure:**
```json
{
      "variables": [
        {
          "isCategorical": true,
          "code": "hypoxic_episode_indicator",
          "sql_type": "text",
          "description": "Hypoxic episode indicator",
          "enumerations": [
            {
              "code": "Yes",
              "label": "Yes"
            },
            {
              "code": "No",
              "label": "No"
            },
            {
              "code": "Unknown",
              "label": "Unknown"
            },
            {
              "code": "Suspected",
              "label": "Suspected"
            }
          ],
          "label": "Hypoxia",
          "units": "",
          "type": "nominal",
          "methodology": ""
        }
      ],
      "code": "Systemic Second Insult",
      "label": "Systemic Second Insult"
    }
```
- Contains a variable for "hypoxic_episode_indicator."
- Uses text values "Yes," "No," "Unknown," or "Suspected" to represent hypoxic episode indicator.


**Mapped FHIR Resource:**
```json
{
  "resourceType": "Observation",
  "id": "systemic-second-insult-example",
  "code": {
    "coding": [
      { "system": "http://loinc.org", "code": "Systemic code", "display": "Systemic Second Insult" }
    ]
  },
  "subject": { "reference": "Patient/patient-example" },
  "component": [
    {
      "code": { "coding": [{ "system": "http://loinc.org", "code": "hypoxic_episode_indicator", "display": "Hypoxic Episode" }] },
      "valueString": "Yes/No/Unknown/Suspected"
    }
  ]
}
```
- Uses the FHIR `Observation` resource.
- Maps "hypoxic_episode_indicator" to a component within the observation.
- Uses LOINC codes for standardized representation.
- Uses text values to represent hypoxic episode indicator.
