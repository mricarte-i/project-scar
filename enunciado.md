# Satellite Calibration Asset Registry (SCAR)

## Context

In Earth Observation missions, raw satellite imagery requires precise radiometric and geometric calibration before it can be transformed into decision-grade products. Calibration & correction assets used for processing evolve over time so the fleet is periodically calibrated.

Your objective is to design and implement a **Satellite Calibration Asset Registry (SCAR)**: the single source of truth for all historical, current, and planned calibration across a fleet of satellites. 

> You are encouraged to use AI-assisted coding tools throughout this exercise.

## Requirements

### Calibration Assets

The registry must manage the following calibration asset for each satellite in the fleet:

|-------------------|-------------------------|-----------------------------|
| **Asset Type**    | **Description**         | **Type**         |
|-------------------|-------------------------|------------------|
| `darkframe`       | A frame characterizing each pixel's offset (sensor response to "no light" input). | 2D array of float values (see sample in attachment) |
| `grayframe`       | A frame characterizing each pixel's relative gain (sensor response to flat gray input). | 2D array of float values (see sample in attachment) |
| `vicarious_cal_gains` | Radiometric vicarious calibration gains and offsets. | JSON file (see sample below) |
| `body_to_payload` | The payload attitude relative to the satellite-coordinates. | JSON file (see sample below) |
|--------------------|-------------------------|------------------|

Each asset is associated with a specific satellite, and is bounded by a temporal validity window. Some assets might be valid "from this date on" (this is the typical case for the last version of each asset)

#### Sample `body_to_payload` JSON structure

```json
{
    "quaternion": [
        0.00808936460768732,
        0.00483359305280839,
        0.004488464035575687,
        0.9999455246407403
    ]
}
``` 

#### Sample `vicarious_cal_gains` JSON structure

```json
{
    "blue": {
        "scale_factor": 0.989,
        "bias_factor": 0
    },
    "green": {
        "scale_factor": 0.956,
        "bias_factor": 0
    },
    "red": {
        "scale_factor": 0.976,
        "bias_factor": 0
    },
    "nir": {
        "scale_factor": 0.904,
        "bias_factor": 0
    }
}
```

### Admin usecase

The system must expose administrative operations to create, update, and retire calibration assets. When a new version of an asset is introduced, it must atomically supersede the previous active version. There must be no temporal overlaps for the same satellite and asset.

This will typically be the case for operators at a new satellite commissoining phase, where the first version of an asset is calibrated, or as a maintenance action during the satellite lifetime.

For example, newsat80 is launched in September 18th 2027. By September 28th 2027 the 4 assets are characterized and operators must upload them for the new satellite. After 6 months, in February 14th 2028, an operator detects that a new grayframe is needed for this satellite and needs to upload it, being valid since February 7th 2028. The new grayframe must now be valid from February 7th 2028 and on, and the previous grayframe must now be valid from September 18th 2027 until February 6th 2028.

### Pipeline usecase

The system must expose a high-throughput read interface optimized for runtime lookups by processing pipelines. It must support:

  1. Point-in-time resolution — given a satellite, asset type, and timestamp, return the exact asset version that was valid at that moment.
  2. Bulk query — given a satellite and timestamp, return all active calibration assets for that satellite at that moment.

Queries for timestamps where no valid asset exists must return clear, unambiguous responses.

### Temporal Versioning

Temporal correctness is the central challenge of this exercise. Your design must ensure that for any given satellite and asset, exactly one version is active at any point in time. You must define and justify how new assets supersede previous ones, how overlaps and gaps are prevented (or handled), and how historical queries are resolved.

### Constraints

- **Python** and **Docker**. The system must run via **Docker Compose**.

## Deliverables

1. Source code in a Git repository.
2. A `README.md` with:
   - Instructions to run the system.
   - Architecture and design decisions with rationale (make sure to include clear assumptions you made or things you'd like to validate that weren't clear enough in this document).
   - Your approach to temporal versioning, including trade-offs and edge cases.
3. Working Docker Compose script.

## Evaluation Criteria

- **Architectural thinking** -- how you decompose the problem, choose technologies, and draw boundaries.
- **Temporal versioning** -- soundness of your versioning model and query resolution logic.
- **Software development lifecycle** -- code quality, testing strategy, CI/CD practices, linting, and overall engineering process maturity.
- **Documentation** -- depth and clarity of your design justifications.

## Bonus

- Observability: structured logging, metrics, health checks.
- Caching and performance optimization for the Pipeline usecase.
- Traceability: keep track of who changed what and when. Maybe even propose a SCAR versioning system to easily track changes in the configurations.