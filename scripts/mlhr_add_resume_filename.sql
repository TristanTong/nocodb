-- mlhr: 保留上传/导入时的原始简历文件名（企微 / 共享盘批量）
-- 2026-08-11

ALTER TABLE mlhr.raw_resume
  ADD COLUMN IF NOT EXISTS resume_filename VARCHAR(255);

ALTER TABLE mlhr.candidate
  ADD COLUMN IF NOT EXISTS resume_filename VARCHAR(255);

COMMENT ON COLUMN mlhr.raw_resume.resume_filename IS '原始简历文件名（含扩展名；非落盘临时名）';
COMMENT ON COLUMN mlhr.candidate.resume_filename IS '原始简历文件名（从简历池晋升时带入）';

-- 存量：从 resume_path 末段回填（企微临时名仍带时间戳前缀，仅作兜底）
UPDATE mlhr.raw_resume
SET resume_filename = regexp_replace(resume_path, '^.*[\\/]', '')
WHERE (resume_filename IS NULL OR resume_filename = '')
  AND resume_path IS NOT NULL
  AND resume_path <> '';

UPDATE mlhr.candidate c
SET resume_filename = r.resume_filename
FROM mlhr.raw_resume r
WHERE c.raw_resume_id = r.id
  AND (c.resume_filename IS NULL OR c.resume_filename = '')
  AND r.resume_filename IS NOT NULL
  AND r.resume_filename <> '';

UPDATE mlhr.candidate
SET resume_filename = regexp_replace(resume_path, '^.*[\\/]', '')
WHERE (resume_filename IS NULL OR resume_filename = '')
  AND resume_path IS NOT NULL
  AND resume_path <> '';
