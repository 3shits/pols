import type { PoolClient } from 'pg';
import { pool } from '../config/db';
import { LookupResolver } from './lookupResolver';
import {
  ParsedFirWorkbook,
  CaseMasterRow,
  ImportResult,
} from '../types/fir.types';

function toDate(value: unknown): Date {
  if (value instanceof Date) return value;
  const d = new Date(String(value));
  if (isNaN(d.getTime())) throw new Error(`Invalid date value: ${value}`);
  return d;
}

/**
 * Imports every FIR ("case") found in the parsed workbook. Each case is
 * inserted in its own transaction so one bad row doesn't roll back the
 * whole file - failures are collected and returned to the caller instead
 * of thrown, so the endpoint can report partial success.
 */
export async function importParsedWorkbook(
  parsed: ParsedFirWorkbook
): Promise<{ results: ImportResult[]; errors: { crimeNo: string; message: string }[] }> {
  const results: ImportResult[] = [];
  const errors: { crimeNo: string; message: string }[] = [];

  for (const caseRow of parsed.caseMaster) {
    const client = await pool.connect();
    try {
      await client.query('BEGIN');
      const result = await importSingleCase(client, caseRow, parsed);
      await client.query('COMMIT');
      results.push(result);
    } catch (err) {
      await client.query('ROLLBACK');
      errors.push({
        crimeNo: caseRow.CrimeNo,
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      client.release();
    }
  }

  return { results, errors };
}

async function importSingleCase(
  client: PoolClient,
  caseRow: CaseMasterRow,
  parsed: ParsedFirWorkbook
): Promise<ImportResult> {
  const lookup = new LookupResolver(client);
  const crimeNo = caseRow.CrimeNo;

  // ---- 1. CaseMaster -------------------------------------------------
  const policePersonId = await lookup.employeeIdByKgid(caseRow.PolicePersonKGID);
  const policeStationId = await lookup.unitIdByStationName(
    caseRow.PoliceStationName,
    caseRow.PoliceStationDistrict
  );
  const caseCategoryId = await lookup.caseCategoryIdByName(caseRow.CaseCategoryName);
  const gravityOffenceId = await lookup.gravityOffenceIdByName(caseRow.GravityOffenceName);
  const crimeMajorHeadId = await lookup.crimeHeadIdByName(caseRow.CrimeMajorHeadName);
  const crimeMinorHeadId = await lookup.crimeSubHeadIdByName(caseRow.CrimeMinorHeadName);
  const caseStatusId = await lookup.caseStatusIdByName(caseRow.CaseStatusName);
  const courtId = await lookup.courtIdByName(caseRow.CourtName);

  const caseInsert = await client.query(
    `INSERT INTO casemaster
       (crimeno, caseno, crimeregistereddate, policepersonid, policestationid,
        casecategoryid, gravityoffenceid, crimemajorheadid, crimeminorheadid,
        casestatusid, courtid, incidentfromdate, incidenttodate, inforeceivedpsdate,
        latitude, longitude, brieffacts)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
     RETURNING casemasterid`,
    [
      crimeNo,
      String(caseRow.CaseNo),
      toDate(caseRow.CrimeRegisteredDate),
      policePersonId,
      policeStationId,
      caseCategoryId,
      gravityOffenceId,
      crimeMajorHeadId,
      crimeMinorHeadId,
      caseStatusId,
      courtId,
      toDate(caseRow.IncidentFromDate),
      toDate(caseRow.IncidentToDate),
      toDate(caseRow.InfoReceivedPSDate),
      caseRow.Latitude,
      caseRow.Longitude,
      caseRow.BriefFacts,
    ]
  );
  const caseMasterId: number = caseInsert.rows[0].casemasterid;

  // ---- 2. ComplainantDetails ------------------------------------------
  const complainants = parsed.complainants.filter((r) => r.LinkCrimeNo === crimeNo);
  for (const c of complainants) {
    const occupationId = await lookup.occupationIdByName(c.OccupationName);
    const religionId = await lookup.religionIdByName(c.ReligionName);
    const casteId = await lookup.casteIdByName(c.CasteName);
    const genderId = lookup.genderIdFromCode(c.Gender);

    await client.query(
      `INSERT INTO complainantdetails
         (casemasterid, complainantname, ageyear, occupationid, religionid, casteid, genderid)
       VALUES ($1,$2,$3,$4,$5,$6,$7)`,
      [caseMasterId, c.ComplainantName, c.AgeYear, occupationId, religionId, casteId, genderId]
    );
  }

  // ---- 3. Victim --------------------------------------------------------
  const victims = parsed.victims.filter((r) => r.LinkCrimeNo === crimeNo);
  for (const v of victims) {
    const genderId = lookup.genderIdFromCode(v.Gender);
    await client.query(
      `INSERT INTO victim (casemasterid, victimname, ageyear, genderid, victimpolice)
       VALUES ($1,$2,$3,$4,$5)`,
      [caseMasterId, v.VictimName, v.AgeYear, genderId, v.VictimPolice]
    );
  }

  // ---- 4. Accused (build PersonID -> AccusedMasterID map for ArrestSurrender) --
  const accusedRows = parsed.accused.filter((r) => r.LinkCrimeNo === crimeNo);
  const accusedIdByPersonId = new Map<string, number>();
  for (const a of accusedRows) {
    const genderId = lookup.genderIdFromCode(a.Gender);
    const inserted = await client.query(
      `INSERT INTO accused (casemasterid, accusedname, ageyear, genderid, personid)
       VALUES ($1,$2,$3,$4,$5)
       RETURNING accusedmasterid`,
      [caseMasterId, a.AccusedName, a.AgeYear, genderId, a.PersonID]
    );
    accusedIdByPersonId.set(a.PersonID, inserted.rows[0].accusedmasterid);
  }

  // ---- 5. ActSectionAssociation ------------------------------------------
  const actSections = parsed.actSections.filter((r) => r.LinkCrimeNo === crimeNo);
  for (const s of actSections) {
    await client.query(
      `INSERT INTO actsectionassociation
         (casemasterid, actid, sectionid, actorderid, sectionorderid)
       VALUES ($1,$2,$3,$4,$5)`,
      [caseMasterId, s.ActCode, s.SectionCode, s.ActOrderID, s.SectionOrderID]
    );
  }

  // ---- 6. ArrestSurrender --------------------------------------------------
  const arrests = parsed.arrestSurrenders.filter((r) => r.LinkCrimeNo === crimeNo);
  for (const ar of arrests) {
    const accusedMasterId = accusedIdByPersonId.get(ar.LinkAccusedPersonID);
    if (!accusedMasterId) {
      throw new Error(
        `ArrestSurrender row references unknown accused PersonID '${ar.LinkAccusedPersonID}' for crime ${crimeNo}`
      );
    }
    const arrestSurrenderTypeId = lookup.arrestSurrenderTypeIdFromName(ar.ArrestSurrenderType);
    const stateId = await lookup.stateIdByName(ar.StateName);
    const districtId = await lookup.districtIdByName(ar.DistrictName);
    const stationId = await lookup.unitIdByStationName(ar.PoliceStationName, ar.DistrictName);
    const ioId = await lookup.employeeIdByKgid(ar.IOKGID);
    const courtIdForArrest = await lookup.courtIdByName(ar.CourtName);

    await client.query(
      `INSERT INTO arrestsurrender
         (casemasterid, arrestsurrendertypeid, arrestsurrenderdate, arrestsurrenderstateid,
          arrestsurrenderdistrictid, policestationid, ioid, courtid, accusedmasterid,
          isaccused, iscomplainantaccused)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)`,
      [
        caseMasterId,
        arrestSurrenderTypeId,
        toDate(ar.ArrestSurrenderDate),
        stateId,
        districtId,
        stationId,
        ioId,
        courtIdForArrest,
        accusedMasterId,
        ar.IsAccused,
        ar.IsComplainantAccused,
      ]
    );
  }

  // ---- 7. ChargesheetDetails ------------------------------------------------
  const chargesheets = parsed.chargesheets.filter((r) => r.LinkCrimeNo === crimeNo);
  for (const cs of chargesheets) {
    const policePersonForCs = await lookup.employeeIdByKgid(cs.PolicePersonKGID);
    await client.query(
      `INSERT INTO chargesheetdetails (casemasterid, csdate, cstype, policepersonid)
       VALUES ($1,$2,$3,$4)`,
      [caseMasterId, toDate(cs.csdate), cs.cstype, policePersonForCs]
    );
  }

  return {
    crimeNo,
    caseMasterId,
    complainants: complainants.length,
    victims: victims.length,
    accused: accusedRows.length,
    actSections: actSections.length,
    arrestSurrenders: arrests.length,
    chargesheets: chargesheets.length,
  };
}
