import type { PoolClient } from 'pg';

/**
 * Resolves human-readable names coming from the spreadsheet (e.g.
 * "Whitefield PS", "Hindu", "Heinous") into the FK IDs the schema expects,
 * with a per-request cache so repeated names across rows only hit the DB once.
 *
 * Table/column names below are lowercase & unquoted, matching sql/schema.sql.
 */
export class LookupResolver {
  private cache = new Map<string, number>();

  constructor(private client: PoolClient) {}

  private cacheKey(table: string, column: string, value: string) {
    return `${table}::${column}::${value.trim().toLowerCase()}`;
  }

  /** Generic single-column name -> id lookup. Throws if not found. */
  async resolve(
    table: string,
    idColumn: string,
    nameColumn: string,
    value: string,
    extra?: { column: string; value: string }
  ): Promise<number> {
    if (!value) {
      throw new Error(`Cannot resolve ${table}.${nameColumn}: empty value`);
    }
    const key = this.cacheKey(table, nameColumn, value + (extra?.value ?? ''));
    const cached = this.cache.get(key);
    if (cached !== undefined) return cached;

    let query = `SELECT ${idColumn} AS id FROM ${table} WHERE ${nameColumn} = $1`;
    const params: unknown[] = [value.trim()];
    if (extra) {
      query += ` AND ${extra.column} = $2`;
      params.push(extra.value.trim());
    }
    query += ' LIMIT 1';

    const result = await this.client.query(query, params);
    if (result.rows.length === 0) {
      throw new Error(
        `Lookup failed: no row in ${table} where ${nameColumn} = '${value}'` +
          (extra ? ` and ${extra.column} = '${extra.value}'` : '')
      );
    }
    const id = Number(result.rows[0].id);
    this.cache.set(key, id);
    return id;
  }

  async employeeIdByKgid(kgid: string): Promise<number> {
    return this.resolve('employee', 'employeeid', 'kgid', kgid);
  }

  async unitIdByStationName(stationName: string, districtName: string): Promise<number> {
    // Disambiguate common station names (e.g. "Town PS") by district.
    const districtId = await this.districtIdByName(districtName);
    const key = this.cacheKey('unit', 'unitname+district', `${stationName}::${districtId}`);
    const cached = this.cache.get(key);
    if (cached !== undefined) return cached;

    const result = await this.client.query(
      `SELECT unitid AS id FROM unit WHERE unitname = $1 AND districtid = $2 LIMIT 1`,
      [stationName.trim(), districtId]
    );
    if (result.rows.length === 0) {
      throw new Error(`Lookup failed: Unit '${stationName}' in district '${districtName}'`);
    }
    const id = Number(result.rows[0].id);
    this.cache.set(key, id);
    return id;
  }

  async stateIdByName(stateName: string): Promise<number> {
    return this.resolve('state', 'stateid', 'statename', stateName);
  }

  async districtIdByName(districtName: string): Promise<number> {
    return this.resolve('district', 'districtid', 'districtname', districtName);
  }

  async courtIdByName(courtName: string): Promise<number> {
    return this.resolve('court', 'courtid', 'courtname', courtName);
  }

  async caseCategoryIdByName(name: string): Promise<number> {
    return this.resolve('casecategory', 'casecategoryid', 'lookupvalue', name);
  }

  async gravityOffenceIdByName(name: string): Promise<number> {
    return this.resolve('gravityoffence', 'gravityoffenceid', 'lookupvalue', name);
  }

  async crimeHeadIdByName(name: string): Promise<number> {
    return this.resolve('crimehead', 'crimeheadid', 'crimegroupname', name);
  }

  async crimeSubHeadIdByName(name: string): Promise<number> {
    return this.resolve('crimesubhead', 'crimesubheadid', 'crimeheadname', name);
  }

  async caseStatusIdByName(name: string): Promise<number> {
    return this.resolve('casestatusmaster', 'casestatusid', 'casestatusname', name);
  }

  async occupationIdByName(name: string): Promise<number> {
    return this.resolve('occupationmaster', 'occupationid', 'occupationname', name);
  }

  async religionIdByName(name: string): Promise<number> {
    return this.resolve('religionmaster', 'religionid', 'religionname', name);
  }

  async casteIdByName(name: string): Promise<number> {
    return this.resolve('castemaster', 'caste_master_id', 'caste_master_name', name);
  }

  /**
   * No GenderMaster table exists in the schema (GenderID is just an int
   * lookup value on each table), so we map the sheet's M/F/T text to a
   * fixed convention. Adjust this map if your GenderMaster differs.
   */
  genderIdFromCode(code: string): number {
    const map: Record<string, number> = { M: 1, F: 2, T: 3 };
    const id = map[(code ?? '').trim().toUpperCase()];
    if (!id) throw new Error(`Unrecognized gender code: '${code}'`);
    return id;
  }

  /**
   * arrestsurrender.arrestsurrendertypeid is an int "lookup value" per the ER
   * doc, but no ArrestSurrenderType master table exists in the schema. The
   * sheet gives a text value ("Arrest" / "Surrender"), so we map it to a
   * fixed convention here, the same way genderIdFromCode works. Adjust this
   * map (or replace it with a real lookup table) if your convention differs.
   */
  arrestSurrenderTypeIdFromName(name: string): number {
    const map: Record<string, number> = { ARREST: 1, SURRENDER: 2 };
    const id = map[(name ?? '').trim().toUpperCase()];
    if (!id) throw new Error(`Unrecognized arrest/surrender type: '${name}'`);
    return id;
  }
}
