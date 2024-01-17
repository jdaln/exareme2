# Introduction to HL7 and FHIR

**HL7 (Health Level Seven)** is a set of international standards for the exchange, integration, sharing, and retrieval of electronic health information. It has been widely used in the healthcare industry to improve interoperability between different healthcare systems.

**FHIR (Fast Healthcare Interoperability Resources)** is a modern healthcare standard developed by HL7. It is designed to simplify healthcare data exchange by providing a framework for representing and exchanging healthcare information in a standardized and structured manner. FHIR is built on modern web standards like JSON and XML, making it accessible and developer-friendly.

FHIR resources represent different aspects of healthcare data and provide a common way to share information among various healthcare systems and applications. Below are some common FHIR resource types along with their descriptions and key attributes.
https://www.hl7.org/fhir/json.html

## HL7 FHIR Resource Types

## 1. Patient

- **Description**: Represents an individual receiving healthcare services.
- **Attributes**:
  - `resourceType` (string): Type of the resource ("Patient").
  - `id` (string): Unique identifier for the patient.
  - `active` (boolean): Indicates whether the patient record is active.
  - `name` (array): Patient's name(s).
  - `telecom` (array): Contact details (phone, email) for the patient.
  - `gender` (code): Patient's gender (male, female, other, etc.).
  - `birthDate` (date): Date of birth of the patient.

## 2. Encounter

- **Description**: Represents a period of time during which healthcare services are provided to a patient.
- **Attributes**:
  - `resourceType` (string): Type of the resource ("Encounter").
  - `id` (string): Unique identifier for the encounter.
  - `status` (code): Current status of the encounter (e.g., "in-progress," "finished").
  - `class` (code): Type of encounter (e.g., "ambulatory," "emergency").
  - `type` (array): Reason for the encounter (e.g., "routine checkup," "emergency room").
  - `period` (Period): Start and end dates/times of the encounter.
  - `subject` (Reference): Reference to the patient involved in the encounter.

## 3. Observation

- **Description**: Represents a single healthcare measurement or observation.
- **Attributes**:
  - `resourceType` (string): Type of the resource ("Observation").
  - `id` (string): Unique identifier for the observation.
  - `status` (code): Current status of the observation (e.g., "final," "preliminary").
  - `category` (array): Type or category of the observation (e.g., "vital-signs," "laboratory").
  - `code` (CodeableConcept): Observation code or name.
  - `subject` (Reference): Reference to the patient for whom the observation was made.
  - `effective[x]` (dateTime or Period): When the observation was made.
  - `value[x]` (various): The result or value of the observation (e.g., quantity, string, codeable concept).
  - `interpretation` (array): Interpretation of the observation result.

## 4. Medication

- **Description**: Represents a medication, including details about its code, form, and manufacturer.
- **Attributes**:
  - `resourceType` (string): Type of the resource ("Medication").
  - `id` (string): Unique identifier for the medication.
  - `code` (CodeableConcept): Medication code or name.
  - `status` (code): Current status of the medication (e.g., "active," "inactive").
  - `manufacturer` (Reference): Reference to the organization that manufactures the medication.
  - `form` (CodeableConcept): Form of the medication (e.g., tablet, capsule).
  - `ingredient` (array): Ingredients composing the medication.

## 5. Practitioner

- **Description**: Represents an individual healthcare provider, such as a physician or nurse.
- **Attributes**:
  - `resourceType` (string): Type of the resource ("Practitioner").
  - `id` (string): Unique identifier for the practitioner.
  - `active` (boolean): Indicates whether the practitioner is currently active.
  - `name` (array): Practitioner's name(s).
  - `telecom` (array): Contact details (phone, email) for the practitioner.
  - `address` (array): Address information for the practitioner.
  - `gender` (code): Practitioner's gender.
  - `qualification` (array): Qualifications and roles of the practitioner.


## Common Labels in HL7 FHIR Resource Types

### 1. `resourceType` (string)

- Description: Specifies the type of FHIR resource being represented (e.g., "Patient," "Encounter," "Observation," etc.).
- Example: `"resourceType": "Patient"`

### 2. `id` (string)

- Description: A unique identifier for the resource within a system.
- Example: `"id": "12345"`

### 3. `meta` (object)

- Description: Contains metadata about the resource, including version information and timestamp of last update.
- Sub-labels:
  - `versionId` (string): The version of the resource.
  - `lastUpdated` (string): The timestamp when the resource was last updated.

```json
"meta": {
    "versionId": "1",
    "lastUpdated": "2024-01-17T12:34:56Z"
}
```

### 4. `text` (object)

- Description: A human-readable representation of the resource, often including a summary or narrative.
- Sub-labels:
  - `status` (string): The status of the text representation (e.g., "generated").
  - `div` (string): The actual text content.

```json
"text": {
    "status": "generated",
    "div": "<div>...</div>"
}
```

### 5. `implicitRules` (uri)

- Description: A URI that provides additional rules and guidance regarding the resource.
- Example: `"implicitRules": "https://example.com/rules"`

### 6. `language` (code)

- Description: The language in which the resource is presented.
- Example: `"language": "en-US"`

### 7. `identifier` (array)

- Description: A list of identifiers associated with the resource, which may include patient IDs, encounter IDs, etc.
- Example:

```json
"identifier": [
    {
        "system": "https://example.com/patient-ids",
        "value": "123456"
    }
]
```

### 8. `contained` (array of objects)

- Description: Embedded resources that are included within the current resource.
- Example:

```json
"contained": [
    {
        "resourceType": "Organization",
        "id": "org1",
        "name": "Example Hospital"
    }
]
```
