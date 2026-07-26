// npm i exceljs
import ExcelJS from 'exceljs';
import {
  ParsedFirWorkbook,
  CaseMasterRow,
  ComplainantRow,
  VictimRow,
  AccusedRow,
  ActSectionRow,
  ArrestSurrenderRow,
  ChargesheetRow,
} from '../types/fir.types';

const REQUIRED_SHEETS = [
  'CaseMaster',
  'ComplainantDetails',
  'Victim',
  'Accused',
  'ActSectionAssociation',
  'ArrestSurrender',
  'ChargesheetDetails',
] as const;

/**
 * Reads every worksheet into an array of plain objects keyed by header row,
 * skipping fully blank rows (the template ships with a blank example row
 * plus trailing empty rows, both of which should be ignored).
 */
function sheetToObjects<T>(worksheet: ExcelJS.Worksheet | undefined): T[] {
  if (!worksheet) return [];

  const headerRow = worksheet.getRow(1);
  const headers: string[] = [];
  headerRow.eachCell({ includeEmpty: false }, (cell, colNumber) => {
    headers[colNumber] = String(cell.value ?? '').trim();
  });

  const rows: T[] = [];
  worksheet.eachRow((row, rowNumber) => {
    if (rowNumber === 1) return; // header

    const obj: Record<string, unknown> = {};
    let hasValue = false;

    row.eachCell({ includeEmpty: true }, (cell, colNumber) => {
      const header = headers[colNumber];
      if (!header) return;
      const value = normalizeCellValue(cell.value);
      obj[header] = value;
      if (value !== null && value !== undefined && value !== '') hasValue = true;
    });

    if (hasValue) rows.push(obj as T);
  });

  return rows;
}

function normalizeCellValue(value: ExcelJS.CellValue): unknown {
  if (value && typeof value === 'object' && 'result' in (value as any)) {
    // formula cell -> use computed result
    return (value as any).result;
  }
  if (value instanceof Date) return value;
  return value ?? null;
}

export async function parseFirWorkbook(fileBuffer: Buffer): Promise<ParsedFirWorkbook> {
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(fileBuffer as any);

  const missing = REQUIRED_SHEETS.filter((name) => !workbook.getWorksheet(name));
  if (missing.length > 0) {
    throw new Error(`Uploaded workbook is missing required sheet(s): ${missing.join(', ')}`);
  }

  const parsed: ParsedFirWorkbook = {
    caseMaster: sheetToObjects<CaseMasterRow>(workbook.getWorksheet('CaseMaster')),
    complainants: sheetToObjects<ComplainantRow>(workbook.getWorksheet('ComplainantDetails')),
    victims: sheetToObjects<VictimRow>(workbook.getWorksheet('Victim')),
    accused: sheetToObjects<AccusedRow>(workbook.getWorksheet('Accused')),
    actSections: sheetToObjects<ActSectionRow>(workbook.getWorksheet('ActSectionAssociation')),
    arrestSurrenders: sheetToObjects<ArrestSurrenderRow>(
      workbook.getWorksheet('ArrestSurrender')
    ),
    chargesheets: sheetToObjects<ChargesheetRow>(workbook.getWorksheet('ChargesheetDetails')),
  };

  if (parsed.caseMaster.length === 0) {
    throw new Error('CaseMaster sheet has no data rows');
  }

  // Filter out the shipped "EXAMPLE-..." demo row so it never gets inserted.
  const isExampleRow = (crimeNo: string | undefined) =>
    !crimeNo || crimeNo.trim().toUpperCase().startsWith('EXAMPLE');

  parsed.caseMaster = parsed.caseMaster.filter((r) => !isExampleRow(r.CrimeNo));
  parsed.complainants = parsed.complainants.filter((r) => !isExampleRow(r.LinkCrimeNo));
  parsed.victims = parsed.victims.filter((r) => !isExampleRow(r.LinkCrimeNo));
  parsed.accused = parsed.accused.filter((r) => !isExampleRow(r.LinkCrimeNo));
  parsed.actSections = parsed.actSections.filter((r) => !isExampleRow(r.LinkCrimeNo));
  parsed.arrestSurrenders = parsed.arrestSurrenders.filter((r) => !isExampleRow(r.LinkCrimeNo));
  parsed.chargesheets = parsed.chargesheets.filter((r) => !isExampleRow(r.LinkCrimeNo));

  return parsed;
}
