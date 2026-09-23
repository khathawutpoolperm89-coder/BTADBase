BEGIN;
ALTER TABLE students ADD COLUMN IF NOT EXISTS line_user_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS students_line_user_id_unique ON students(line_user_id) WHERE line_user_id IS NOT NULL;
COMMIT;
