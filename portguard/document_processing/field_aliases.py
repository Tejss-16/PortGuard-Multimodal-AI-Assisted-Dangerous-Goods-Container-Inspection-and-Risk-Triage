
# field_aliases.py
# Alternative labels for the 13 fields required by PortGuard.

FIELD_ALIASES = {
    "un_number": [
        "UN",
        "UN Number",
        "UN Number or ID Number",
        "UN_Number",
        "UN No.",
        "UN No",
        "United Nations Number",
        "UNNO",
    ],

    "proper_shipping_name": [
        "Proper Shipping Name",
        "UN Proper Shipping Name",
        "Proper_Shipping_Name",
        "Shipping Name",
        "Shipping_Name",
        "PSN",
        "Official Shipping Name",
    ],

    "imdg_class": [
        "IMDG Class",
        "IMDG_Class",
        "Hazard Class",
        "Hazard_Class",
        "Primary Class",
        "Primary Hazard Class",
        "Class of Dangerous Goods",
        "Transport Hazard Class",
        "Transport Hazard Class(es)",
        "Hazard Class Shown",
        "Hazard Class Declared",
    ],

    "subsidiary_hazard": [
        "Subsidiary Hazard",
        "Subsidiary_Hazard",
        "Subsidiary Risk",
        "Subsidiary Class",
        "Additional Hazard Class",
        "Secondary Hazard",
    ],

    "packing_group": [
        "Packing Group",
        "Packing_Group",
        "Packing Group Number",
        "Packing Group (if applicable)",
        "Packing_Group_Number",
        "PG",
        "Packaging Group",
    ],

    "container_number": [
        "Container Number",
        "Container_Number",
        "Container No.",
        "Container No",
        "Container ID",
        "Container_ID",
        "Container Identification Number",
        "Container Identification No.",
        "CTU Identification Number",
    ],

    "seal_number": [
        "Seal Number",
        "Seal_Number",
        "Seal No.",
        "Seal No",
        "Seal ID",
        "Seal_ID",
        "Container Seal Number",
    ],

    "gross_weight_kg": [
    "Gross Weight",
    "Gross_Weight",
    "Gross Weight (kg)",
    "Gross Mass",
    "Gross_Mass",
    "Gross Mass (kg)",
    "Cargo Gross Weight",
    "Cargo Gross Mass"
],

    "net_weight_kg": [
        "Net Weight",
        "Net_Weight",
        "Net Weight (kg)",
        "Net Mass",
        "Net_Mass",
        "Net Mass (kg)",
        "Cargo Net Weight",
    ],

    "marine_pollutant": [
        "Marine Pollutant",
        "Marine_Pollutant",
        "Marine Pollutant Status",
        "Marine Pollutant (Yes/No)",
        "Marine Pollutant Indicator",
    ],

    "ems_code": [
    "EMS",
    "EMS Code",
    "EMS_Code",
    "Emergency Schedule",
    "Emergency Schedule Code",
    "EmS",
    "EmS Number",
],

"ems_fire": [
    "EMS Fire",
    "Fire EMS",
],

"ems_spillage": [
    "EMS Spillage",
    "Spillage EMS",
],

    "port_of_loading": [
        "Port of Loading",
        "Port_of_Loading",
        "Port / Place of Loading",
        "Port/Place of Loading",
        "Loading Port",
        "Loading_Port",
        "POL",
    ],

    "port_of_discharge": [
        "Port of Discharge",
        "Port_of_Discharge",
        "Port / Place of Discharge",
        "Port/Place of Discharge",
        "Discharge Port",
        "Discharge_Port",
        "POD",
    ],
}
