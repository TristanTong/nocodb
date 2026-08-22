
CREATE SCHEMA IF NOT EXISTS mlhr;

-- 岗位需求
CREATE TABLE IF NOT EXISTS mlhr.job_req (
  id              BIGSERIAL PRIMARY KEY,
  job_name        VARCHAR(200) NOT NULL,
  department      VARCHAR(100),
  headcount       INT DEFAULT 1,
  status          VARCHAR(32) NOT NULL DEFAULT 'open',
  owner_hr        VARCHAR(100),
  remark          TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 泛简历池
CREATE TABLE IF NOT EXISTS mlhr.raw_resume (
  id                      BIGSERIAL PRIMARY KEY,
  original_name           VARCHAR(100),
  name_trust              VARCHAR(32) NOT NULL DEFAULT 'none',
  mobile                  VARCHAR(32),
  email                   VARCHAR(200),
  education               VARCHAR(32),
  school                  VARCHAR(200),
  major                   VARCHAR(200),
  work_years              NUMERIC(6,1),
  company_latest          VARCHAR(200),
  title_target            VARCHAR(200),
  skills                  TEXT,
  source_channel          VARCHAR(64),
  file_md5                VARCHAR(64),
  resume_path             TEXT,
  resume_file_url         TEXT,
  resume_filename         VARCHAR(255),
  pool_status             VARCHAR(32) NOT NULL DEFAULT 'pending_check',
  parse_raw_json          TEXT,
  created_by              VARCHAR(100),
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  promoted_candidate_id   BIGINT
);

CREATE INDEX IF NOT EXISTS idx_raw_resume_mobile ON mlhr.raw_resume (mobile);
CREATE INDEX IF NOT EXISTS idx_raw_resume_email ON mlhr.raw_resume (email);
CREATE INDEX IF NOT EXISTS idx_raw_resume_md5 ON mlhr.raw_resume (file_md5);
CREATE INDEX IF NOT EXISTS idx_raw_resume_status ON mlhr.raw_resume (pool_status);
CREATE INDEX IF NOT EXISTS idx_raw_resume_created ON mlhr.raw_resume (created_at);

-- 候选人正式表
CREATE TABLE IF NOT EXISTS mlhr.candidate (
  id                  BIGSERIAL PRIMARY KEY,
  candidate_no        VARCHAR(32) NOT NULL,
  name                VARCHAR(100) NOT NULL,
  name_trust          VARCHAR(32) NOT NULL DEFAULT 'real',
  mobile              VARCHAR(32) NOT NULL,
  email               VARCHAR(200),
  education           VARCHAR(32),
  school              VARCHAR(200),
  major               VARCHAR(200),
  work_years          NUMERIC(6,1),
  company_latest      VARCHAR(200),
  title_target        VARCHAR(200),
  skills              TEXT,
  source_channel      VARCHAR(64),
  job_family          VARCHAR(64),
  job_title_cat       VARCHAR(100),
  resume_path         TEXT,
  resume_file_url     TEXT,
  resume_filename     VARCHAR(255),
  raw_resume_id       BIGINT REFERENCES mlhr.raw_resume(id),
  status              VARCHAR(32) NOT NULL DEFAULT '待筛选',
  grade               VARCHAR(8),
  intent_level        VARCHAR(16),
  target_position_ids TEXT,
  owner_hr            VARCHAR(100),
  next_follow_at      DATE,
  remark              TEXT,
  source_detail       VARCHAR(64),
  duplicate_flag      VARCHAR(16) NOT NULL DEFAULT 'none',
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_by          VARCHAR(100),
  CONSTRAINT uq_candidate_no UNIQUE (candidate_no),
  CONSTRAINT uq_candidate_name_mobile UNIQUE (name, mobile)
);

CREATE INDEX IF NOT EXISTS idx_candidate_status ON mlhr.candidate (status);
CREATE INDEX IF NOT EXISTS idx_candidate_owner ON mlhr.candidate (owner_hr);
CREATE INDEX IF NOT EXISTS idx_candidate_title ON mlhr.candidate (title_target);
CREATE INDEX IF NOT EXISTS idx_candidate_skills ON mlhr.candidate (skills);
CREATE INDEX IF NOT EXISTS idx_candidate_follow ON mlhr.candidate (next_follow_at);

-- 回写外键（晋升后）
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_raw_promoted_candidate'
  ) THEN
    ALTER TABLE mlhr.raw_resume
      ADD CONSTRAINT fk_raw_promoted_candidate
      FOREIGN KEY (promoted_candidate_id) REFERENCES mlhr.candidate(id);
  END IF;
END $$;

-- 面评（P1，先建表）
CREATE TABLE IF NOT EXISTS mlhr.interview_note (
  id              BIGSERIAL PRIMARY KEY,
  candidate_id    BIGINT NOT NULL REFERENCES mlhr.candidate(id),
  interviewer     VARCHAR(100),
  round_no        INT DEFAULT 1,
  level_tag       VARCHAR(32),
  interview_at    TIMESTAMPTZ,
  result          VARCHAR(64),
  comment         TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_interview_candidate ON mlhr.interview_note (candidate_id);

-- 操作日志
CREATE TABLE IF NOT EXISTS mlhr.op_log (
  id              BIGSERIAL PRIMARY KEY,
  actor           VARCHAR(100),
  action          VARCHAR(64) NOT NULL,
  source_table    VARCHAR(64),
  record_id       VARCHAR(64),
  summary         TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_op_log_created ON mlhr.op_log (created_at);

COMMENT ON SCHEMA mlhr IS 'MIDP 人才库/人事一期 schema（IT-AI-2026-003）';
COMMENT ON TABLE mlhr.raw_resume IS '泛简历池：全量解析首站';
COMMENT ON TABLE mlhr.candidate IS '候选人正式表：姓名校验通过后晋升';
COMMENT ON TABLE mlhr.job_req IS '岗位需求';
COMMENT ON TABLE mlhr.interview_note IS '面试评价';
COMMENT ON TABLE mlhr.op_log IS '操作审计';
