-- candidate：上传人/创建人溯源（与 raw_resume.created_by 对齐）
-- 2026-08-11

ALTER TABLE mlhr.candidate
  ADD COLUMN IF NOT EXISTS created_by VARCHAR(100);

COMMENT ON COLUMN mlhr.candidate.created_by IS '简历上传人/创建人（通常来自 raw_resume.created_by）';

UPDATE mlhr.candidate c
SET created_by = r.created_by
FROM mlhr.raw_resume r
WHERE c.raw_resume_id = r.id
  AND (c.created_by IS NULL OR c.created_by = '')
  AND r.created_by IS NOT NULL
  AND r.created_by <> '';

UPDATE mlhr.candidate
SET created_by = updated_by
WHERE (created_by IS NULL OR created_by = '')
  AND updated_by IS NOT NULL
  AND updated_by <> '';
