-- =====================================================================
-- Karnataka Police FIR System - PostgreSQL Schema (prototype)
-- Generated from ER Diagram document
--
-- NOTE: all identifiers are lowercase & unquoted (Postgres folds unquoted
-- identifiers to lowercase automatically). This matches the raw SQL used
-- by the Excel-import feature (services/firImportService.ts, lookupResolver.ts),
-- so no quoting is required anywhere in the app.
-- =====================================================================

-- ---------- Base / geo tables ----------
CREATE TABLE IF NOT EXISTS state (
    stateid SERIAL PRIMARY KEY,
    statename VARCHAR(150) NOT NULL,
    nationalityid INT,
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS district (
    districtid SERIAL PRIMARY KEY,
    districtname VARCHAR(150) NOT NULL,
    stateid INT REFERENCES state(stateid),
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS court (
    courtid SERIAL PRIMARY KEY,
    courtname VARCHAR(200) NOT NULL,
    districtid INT REFERENCES district(districtid),
    stateid INT REFERENCES state(stateid),
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS unittype (
    unittypeid SERIAL PRIMARY KEY,
    unittypename VARCHAR(150) NOT NULL,
    citydiststate VARCHAR(50),
    hierarchy INT,
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS unit (
    unitid SERIAL PRIMARY KEY,
    unitname VARCHAR(200) NOT NULL,
    typeid INT REFERENCES unittype(unittypeid),
    parentunit INT REFERENCES unit(unitid),
    nationalityid INT,
    stateid INT REFERENCES state(stateid),
    districtid INT REFERENCES district(districtid),
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS rank (
    rankid SERIAL PRIMARY KEY,
    rankname VARCHAR(150) NOT NULL,
    hierarchy INT,
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS designation (
    designationid SERIAL PRIMARY KEY,
    designationname VARCHAR(150) NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    sortorder INT
);

CREATE TABLE IF NOT EXISTS employee (
    employeeid SERIAL PRIMARY KEY,
    districtid INT REFERENCES district(districtid),
    unitid INT REFERENCES unit(unitid),
    rankid INT REFERENCES rank(rankid),
    designationid INT REFERENCES designation(designationid),
    kgid VARCHAR(50) UNIQUE,
    firstname VARCHAR(150),
    employeedob DATE,
    genderid INT,
    bloodgroupid INT,
    physicallychallenged BOOLEAN DEFAULT FALSE,
    appointmentdate DATE
);

-- ---------- Lookup / master tables ----------
CREATE TABLE IF NOT EXISTS casecategory (
    casecategoryid SERIAL PRIMARY KEY,
    lookupvalue VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS gravityoffence (
    gravityoffenceid SERIAL PRIMARY KEY,
    lookupvalue VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS crimehead (
    crimeheadid SERIAL PRIMARY KEY,
    crimegroupname VARCHAR(200) NOT NULL,
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS crimesubhead (
    crimesubheadid SERIAL PRIMARY KEY,
    crimeheadid INT REFERENCES crimehead(crimeheadid),
    crimeheadname VARCHAR(200) NOT NULL,
    seqid INT
);

CREATE TABLE IF NOT EXISTS act (
    actcode VARCHAR(30) PRIMARY KEY,
    actdescription VARCHAR(300) NOT NULL,
    shortname VARCHAR(100),
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS section (
    sectioncode VARCHAR(30) PRIMARY KEY,
    actcode VARCHAR(30) REFERENCES act(actcode),
    sectiondescription VARCHAR(300),
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS crimeheadactsection (
    crimeheadactsectionid SERIAL PRIMARY KEY,
    crimeheadid INT REFERENCES crimehead(crimeheadid),
    actcode VARCHAR(30) REFERENCES act(actcode),
    sectioncode VARCHAR(30) REFERENCES section(sectioncode)
);

CREATE TABLE IF NOT EXISTS castemaster (
    caste_master_id SERIAL PRIMARY KEY,
    caste_master_name VARCHAR(150) NOT NULL
);

CREATE TABLE IF NOT EXISTS religionmaster (
    religionid SERIAL PRIMARY KEY,
    religionname VARCHAR(150) NOT NULL
);

CREATE TABLE IF NOT EXISTS occupationmaster (
    occupationid SERIAL PRIMARY KEY,
    occupationname VARCHAR(150) NOT NULL
);

CREATE TABLE IF NOT EXISTS casestatusmaster (
    casestatusid SERIAL PRIMARY KEY,
    casestatusname VARCHAR(150) NOT NULL
);

-- ---------- Core FIR entities ----------
CREATE TABLE IF NOT EXISTS casemaster (
    casemasterid SERIAL PRIMARY KEY,
    crimeno VARCHAR(50) UNIQUE,
    caseno VARCHAR(50),
    crimeregistereddate DATE,
    policepersonid INT REFERENCES employee(employeeid),
    policestationid INT REFERENCES unit(unitid),
    casecategoryid INT REFERENCES casecategory(casecategoryid),
    gravityoffenceid INT REFERENCES gravityoffence(gravityoffenceid),
    crimemajorheadid INT REFERENCES crimehead(crimeheadid),
    crimeminorheadid INT REFERENCES crimesubhead(crimesubheadid),
    casestatusid INT REFERENCES casestatusmaster(casestatusid),
    courtid INT REFERENCES court(courtid),
    incidentfromdate TIMESTAMP,
    incidenttodate TIMESTAMP,
    inforeceivedpsdate TIMESTAMP,
    latitude DECIMAL(10,6),
    longitude DECIMAL(10,6),
    brieffacts TEXT
);

CREATE TABLE IF NOT EXISTS inv_occurancetime (
    casemasterid INT PRIMARY KEY REFERENCES casemaster(casemasterid) ON DELETE CASCADE,
    occurrencefromdate TIMESTAMP,
    occurrencetodate TIMESTAMP,
    occurrenceplace VARCHAR(300)
);

CREATE TABLE IF NOT EXISTS complainantdetails (
    complainantid SERIAL PRIMARY KEY,
    casemasterid INT REFERENCES casemaster(casemasterid) ON DELETE CASCADE,
    complainantname VARCHAR(200) NOT NULL,
    ageyear INT,
    occupationid INT REFERENCES occupationmaster(occupationid),
    religionid INT REFERENCES religionmaster(religionid),
    casteid INT REFERENCES castemaster(caste_master_id),
    genderid INT
);

CREATE TABLE IF NOT EXISTS actsectionassociation (
    actsectionassociationid SERIAL PRIMARY KEY,
    casemasterid INT REFERENCES casemaster(casemasterid) ON DELETE CASCADE,
    actid VARCHAR(30) REFERENCES act(actcode),
    sectionid VARCHAR(30) REFERENCES section(sectioncode),
    actorderid INT,
    sectionorderid INT
);

CREATE TABLE IF NOT EXISTS victim (
    victimmasterid SERIAL PRIMARY KEY,
    casemasterid INT REFERENCES casemaster(casemasterid) ON DELETE CASCADE,
    victimname VARCHAR(200) NOT NULL,
    ageyear INT,
    genderid INT,
    victimpolice BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS accused (
    accusedmasterid SERIAL PRIMARY KEY,
    casemasterid INT REFERENCES casemaster(casemasterid) ON DELETE CASCADE,
    accusedname VARCHAR(200) NOT NULL,
    ageyear INT,
    genderid INT,
    personid VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS arrestsurrender (
    arrestsurrenderid SERIAL PRIMARY KEY,
    casemasterid INT REFERENCES casemaster(casemasterid) ON DELETE CASCADE,
    arrestsurrendertypeid INT,
    arrestsurrenderdate DATE,
    arrestsurrenderstateid INT REFERENCES state(stateid),
    arrestsurrenderdistrictid INT REFERENCES district(districtid),
    policestationid INT REFERENCES unit(unitid),
    ioid INT REFERENCES employee(employeeid),
    courtid INT REFERENCES court(courtid),
    accusedmasterid INT REFERENCES accused(accusedmasterid),
    isaccused BOOLEAN DEFAULT FALSE,
    iscomplainantaccused BOOLEAN DEFAULT FALSE
);

-- Junction: one arrest/surrender event can link multiple accused
CREATE TABLE IF NOT EXISTS inv_arrestsurrenderaccused (
    invarrestsurrenderaccusedid SERIAL PRIMARY KEY,
    arrestsurrenderid INT REFERENCES arrestsurrender(arrestsurrenderid) ON DELETE CASCADE,
    accusedmasterid INT REFERENCES accused(accusedmasterid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chargesheetdetails (
    csid SERIAL PRIMARY KEY,
    casemasterid INT REFERENCES casemaster(casemasterid) ON DELETE CASCADE,
    csdate TIMESTAMP,
    cstype CHAR(1) CHECK (cstype IN ('A','B','C')),
    policepersonid INT REFERENCES employee(employeeid)
);

-- Helpful indexes on common FK lookups
CREATE INDEX IF NOT EXISTS idx_casemaster_station ON casemaster(policestationid);
CREATE INDEX IF NOT EXISTS idx_casemaster_category ON casemaster(casecategoryid);
CREATE INDEX IF NOT EXISTS idx_victim_case ON victim(casemasterid);
CREATE INDEX IF NOT EXISTS idx_accused_case ON accused(casemasterid);
CREATE INDEX IF NOT EXISTS idx_complainant_case ON complainantdetails(casemasterid);
CREATE INDEX IF NOT EXISTS idx_arrestsurrender_case ON arrestsurrender(casemasterid);
CREATE INDEX IF NOT EXISTS idx_actsection_case ON actsectionassociation(casemasterid);
CREATE INDEX IF NOT EXISTS idx_unit_name_district ON unit(unitname, districtid);
