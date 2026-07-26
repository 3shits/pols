import { Router } from "express";
import { createCrudRouter, TableConfig } from "../utils/crudFactory";

// Every table from the ER diagram, mapped to a REST resource.
// Add/remove columns here if the schema changes - no other code needs touching.
// Table/column names are lowercase & unquoted, matching sql/schema.sql and the
// raw SQL used by the Excel-import feature (services/firImportService.ts).
const tableConfigs: TableConfig[] = [
  { resource: "states", table: "state", pk: "stateid", columns: ["statename", "nationalityid", "active"] },
  { resource: "districts", table: "district", pk: "districtid", columns: ["districtname", "stateid", "active"] },
  { resource: "courts", table: "court", pk: "courtid", columns: ["courtname", "districtid", "stateid", "active"] },
  { resource: "unit-types", table: "unittype", pk: "unittypeid", columns: ["unittypename", "citydiststate", "hierarchy", "active"] },
  { resource: "units", table: "unit", pk: "unitid", columns: ["unitname", "typeid", "parentunit", "nationalityid", "stateid", "districtid", "active"] },
  { resource: "ranks", table: "rank", pk: "rankid", columns: ["rankname", "hierarchy", "active"] },
  { resource: "designations", table: "designation", pk: "designationid", columns: ["designationname", "active", "sortorder"] },
  {
    resource: "employees",
    table: "employee",
    pk: "employeeid",
    columns: [
      "districtid", "unitid", "rankid", "designationid", "kgid", "firstname",
      "employeedob", "genderid", "bloodgroupid", "physicallychallenged", "appointmentdate",
    ],
  },
  { resource: "case-categories", table: "casecategory", pk: "casecategoryid", columns: ["lookupvalue"] },
  { resource: "gravity-offences", table: "gravityoffence", pk: "gravityoffenceid", columns: ["lookupvalue"] },
  { resource: "crime-heads", table: "crimehead", pk: "crimeheadid", columns: ["crimegroupname", "active"] },
  { resource: "crime-sub-heads", table: "crimesubhead", pk: "crimesubheadid", columns: ["crimeheadid", "crimeheadname", "seqid"] },
  { resource: "acts", table: "act", pk: "actcode", manualPk: true, columns: ["actdescription", "shortname", "active"] },
  { resource: "sections", table: "section", pk: "sectioncode", manualPk: true, columns: ["actcode", "sectiondescription", "active"] },
  { resource: "crime-head-act-sections", table: "crimeheadactsection", pk: "crimeheadactsectionid", columns: ["crimeheadid", "actcode", "sectioncode"] },
  { resource: "castes", table: "castemaster", pk: "caste_master_id", columns: ["caste_master_name"] },
  { resource: "religions", table: "religionmaster", pk: "religionid", columns: ["religionname"] },
  { resource: "occupations", table: "occupationmaster", pk: "occupationid", columns: ["occupationname"] },
  { resource: "case-statuses", table: "casestatusmaster", pk: "casestatusid", columns: ["casestatusname"] },
  {
    resource: "cases",
    table: "casemaster",
    pk: "casemasterid",
    columns: [
      "crimeno", "caseno", "crimeregistereddate", "policepersonid", "policestationid",
      "casecategoryid", "gravityoffenceid", "crimemajorheadid", "crimeminorheadid",
      "casestatusid", "courtid", "incidentfromdate", "incidenttodate", "inforeceivedpsdate",
      "latitude", "longitude", "brieffacts",
    ],
  },
  {
    resource: "occurrence-times",
    table: "inv_occurancetime",
    pk: "casemasterid",
    manualPk: true, // shares PK with casemaster (1:1), not auto-generated
    columns: ["occurrencefromdate", "occurrencetodate", "occurrenceplace"],
  },
  {
    resource: "complainants",
    table: "complainantdetails",
    pk: "complainantid",
    columns: ["casemasterid", "complainantname", "ageyear", "occupationid", "religionid", "casteid", "genderid"],
  },
  {
    resource: "act-section-associations",
    table: "actsectionassociation",
    pk: "actsectionassociationid",
    columns: ["casemasterid", "actid", "sectionid", "actorderid", "sectionorderid"],
  },
  {
    resource: "victims",
    table: "victim",
    pk: "victimmasterid",
    columns: ["casemasterid", "victimname", "ageyear", "genderid", "victimpolice"],
  },
  {
    resource: "accused",
    table: "accused",
    pk: "accusedmasterid",
    columns: ["casemasterid", "accusedname", "ageyear", "genderid", "personid"],
  },
  {
    resource: "arrest-surrenders",
    table: "arrestsurrender",
    pk: "arrestsurrenderid",
    columns: [
      "casemasterid", "arrestsurrendertypeid", "arrestsurrenderdate", "arrestsurrenderstateid",
      "arrestsurrenderdistrictid", "policestationid", "ioid", "courtid", "accusedmasterid",
      "isaccused", "iscomplainantaccused",
    ],
  },
  {
    resource: "arrest-surrender-accused-links",
    table: "inv_arrestsurrenderaccused",
    pk: "invarrestsurrenderaccusedid",
    columns: ["arrestsurrenderid", "accusedmasterid"],
  },
  {
    resource: "chargesheets",
    table: "chargesheetdetails",
    pk: "csid",
    columns: ["casemasterid", "csdate", "cstype", "policepersonid"],
  },
];

export function buildApiRouter(): Router {
  const router = Router();

  router.get("/", (_req, res) => {
    res.json({
      message: "Karnataka Police FIR System API (prototype)",
      resources: tableConfigs.map((c) => `/api/${c.resource}`),
      uploadEndpoint: "/api/fir/upload",
    });
  });

  for (const config of tableConfigs) {
    router.use(`/${config.resource}`, createCrudRouter(config));
  }

  return router;
}
