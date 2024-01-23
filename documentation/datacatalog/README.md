# Data Catalog for Medical Data Documentation

## Entities

### Data Models
A representation of a specific medical condition or disease in the catalog. Data Models contain various data points and metadata and support versioning.

### Data Model Groups
Categorization within a specific Data Model to organize related variables. These groups help structure the Data Model, and their configurations may vary across different versions of the Data Model.

### Common Data Elements (CDEs)
Standard data element across multiple datasets of a Data Model. CDEs ensure consistency in data collection within Data Models.

### Datasets
Collections of data, often in the form of CSV files, that are associated with specific Data Models. These datasets adhere to the structure defined by the CDEsMetadata to maintain uniformity.

### CDEsMetadata
A JSON file crucial for specifying the structure and type of variables (CDEs) within a data model. It defines how data should be formatted and organized across different datasets of a specific Data Model, ensuring consistency and standardization.
An example can be seen at [CDEs Medatadata](../../tests/test_data/dementia_v_0_1/CDEsMetadata.json)


## User Personas

### Guest
Guests have read-only access to the Data Catalog. They can view Data Models, their associated Data Model Groups, CDEs, Datasets, including dataset locations, and the amount of records per Data Model. Guests can also access different versions of these Data Models.

### Domain Expert
A Domain Expert is responsible for managing a single, specific Data Model. They can create new Data Models, but these models are not visible to the public until flagged as released. Once a Data Model is released, it can no longer be edited, and any changes require creating a new version. Domain Experts also oversee Data Model Groups, CDEs, and Datasets within their assigned Data Model.

## Actions by User Persona

### Actions Available to a Guest
- **View Data Models**: Access and view details of different Data Models and their versions.
- **View Data Model Groups**: See how variables are organized within each Data Model.
- **View CDEs**: Examine the standard data elements used in various Data Models.
- **View Datasets**: Look at the datasets associated with each Data Model, including their locations.
- **View Amount of Records per Data Model**: Access information on the number of records within each Data Model.

### Actions Available to a Domain Expert
- **Create New Data Model**: Domain Experts can create new Data Models, but these models are not visible to the public until flagged as released.
- **Flag Data Model as Released**: Once a Data Model is complete and ready for public visibility, Domain Experts can flag it as released.
- **Manage Data Model Groups within Their Data Model**: Organize and restructure variables within their assigned Data Model as needed.
- **Manage CDEs within Their Data Model**: Ensure the uniformity and applicability of CDEs within their assigned Data Model.
- **Associate Datasets with Their Data Model**: Link relevant datasets to their specific Data Model, adhering to the CDEsMetadata structure.
- **Create New Version of Released Data Model**: If changes are needed after a Data Model is released, Domain Experts can create a new version while preserving the original version's integrity.
