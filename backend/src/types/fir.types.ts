/**
 * Types mirroring the sheets in the FIR import workbook and the
 * corresponding DB entities described in the ER diagram.
 */

export interface CaseMasterRow {
  CrimeNo: string;
  CaseNo: string | number;
  CrimeRegisteredDate: string | Date;
  PolicePersonKGID: string;
  PoliceStationName: string;
  PoliceStationDistrict: string;
  CaseCategoryName: string;
  GravityOffenceName: string;
  CrimeMajorHeadName: string;
  CrimeMinorHeadName: string;
  CaseStatusName: string;
  CourtName: string;
  IncidentFromDate: string | Date;
  IncidentToDate: string | Date;
  InfoReceivedPSDate: string | Date;
  Latitude: number;
  Longitude: number;
  BriefFacts: string;
}

export interface ComplainantRow {
  LinkCrimeNo: string;
  ComplainantName: string;
  AgeYear: number;
  OccupationName: string;
  ReligionName: string;
  CasteName: string;
  Gender: string; // M / F / T
}

export interface VictimRow {
  LinkCrimeNo: string;
  VictimName: string;
  AgeYear: number;
  Gender: string;
  VictimPolice: number; // 0 / 1
}

export interface AccusedRow {
  LinkCrimeNo: string;
  PersonID: string; // e.g. A1, A2 - sheet-local identifier
  AccusedName: string;
  AgeYear: number;
  Gender: string;
}

export interface ActSectionRow {
  LinkCrimeNo: string;
  ActCode: string;
  SectionCode: string;
  ActOrderID: number;
  SectionOrderID: number;
}

export interface ArrestSurrenderRow {
  LinkCrimeNo: string;
  LinkAccusedPersonID: string; // matches AccusedRow.PersonID
  ArrestSurrenderType: string;
  ArrestSurrenderDate: string | Date;
  StateName: string;
  DistrictName: string;
  PoliceStationName: string;
  IOKGID: string;
  CourtName: string;
  IsAccused: number;
  IsComplainantAccused: number;
}

export interface ChargesheetRow {
  LinkCrimeNo: string;
  csdate: string | Date;
  cstype: string; // A / B / C
  PolicePersonKGID: string;
}

/** Everything parsed out of one uploaded workbook, grouped by sheet. */
export interface ParsedFirWorkbook {
  caseMaster: CaseMasterRow[];
  complainants: ComplainantRow[];
  victims: VictimRow[];
  accused: AccusedRow[];
  actSections: ActSectionRow[];
  arrestSurrenders: ArrestSurrenderRow[];
  chargesheets: ChargesheetRow[];
}

export interface ImportResult {
  crimeNo: string;
  caseMasterId: number;
  complainants: number;
  victims: number;
  accused: number;
  actSections: number;
  arrestSurrenders: number;
  chargesheets: number;
}

export interface UploadResponse {
  stratusObjectKey: string;
  stratusObjectUrl?: string;
  totalCases: number;
  results: ImportResult[];
  errors: { crimeNo: string; message: string }[];
}
