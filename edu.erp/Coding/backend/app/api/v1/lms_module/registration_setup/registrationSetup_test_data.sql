-- Registration Setup API: safe test data helpers (MySQL 8+)
-- Run each section deliberately. Review the SELECT output before running INSERT,
-- UPDATE, or DELETE statements in a shared environment.

-- ---------------------------------------------------------------------------
-- 1. Pick one existing active academic batch and semester for testing.
--    Replace these values manually if you need a specific batch or semester.
-- ---------------------------------------------------------------------------
SET @academic_batch_id := (
    SELECT academic_batch_id
    FROM iems_academic_batch
    WHERE status = 1
    ORDER BY academic_batch_id
    LIMIT 1
);

SET @semester_id := (
    SELECT semester_id
    FROM iems_semester
    WHERE academic_batch_id = @academic_batch_id
      AND status = 1
    ORDER BY semester_id
    LIMIT 1
);

SET @semester_number := (
    SELECT semester
    FROM iems_semester
    WHERE semester_id = @semester_id
);

SET @test_user_id := (SELECT id FROM iems_users ORDER BY id LIMIT 1);

-- ---------------------------------------------------------------------------
-- 2. Pre-flight: inspect selected records and any existing setup.
-- ---------------------------------------------------------------------------
SELECT
    @academic_batch_id AS academic_batch_id,
    @semester_id AS semester_id,
    @semester_number AS semester_number,
    @test_user_id AS test_user_id;

SELECT
    batch.academic_batch_id,
    batch.academic_batch_desc,
    semester.semester_id,
    semester.term_name,
    semester.enroll_start_date,
    semester.enroll_start_time,
    semester.enroll_end_date,
    semester.enroll_end_time,
    semester.total_crs_enroll,
    semester.own_crclm_elective,
    semester.other_crclm_elective
FROM iems_academic_batch AS batch
JOIN iems_semester AS semester
    ON semester.academic_batch_id = batch.academic_batch_id
WHERE batch.academic_batch_id = @academic_batch_id
  AND semester.semester_id = @semester_id;

SELECT
    structure.ctcs_id,
    course_type.course_type_desc,
    structure.crs_type_total,
    structure.stud_min_crs_enroll,
    structure.stud_max_crs_enroll
FROM lms_academic_batch_semester_crs_structure AS structure
JOIN iems_course_type AS course_type
    ON course_type.course_type_id = structure.crs_type_id
WHERE structure.academic_batch_id = @academic_batch_id
  AND structure.semester_id = @semester_id
ORDER BY course_type.course_type_desc;

-- ---------------------------------------------------------------------------
-- 3. Add test setup data. This inserts only missing course-type rows.
--    Existing records are never overwritten by this section.
-- ---------------------------------------------------------------------------
START TRANSACTION;

UPDATE iems_semester
SET
    enroll_start_date = CURDATE(),
    enroll_start_time = '09:00:00',
    enroll_end_date = DATE_ADD(CURDATE(), INTERVAL 7 DAY),
    enroll_end_time = '17:00:00',
    total_crs_enroll = 20.0,
    own_crclm_elective = 1,
    other_crclm_elective = 1,
    modified_by = @test_user_id,
    modify_date = NOW()
WHERE semester_id = @semester_id
  AND academic_batch_id = @academic_batch_id;

INSERT INTO lms_academic_batch_semester_crs_structure (
    academic_batch_id,
    semester_id,
    crs_type_id,
    crs_type_total,
    stud_min_crs_enroll,
    stud_max_crs_enroll,
    created_by,
    created_date
)
SELECT
    @academic_batch_id,
    @semester_id,
    course.course_type_id,
    LEAST(COALESCE(SUM(course.total_credits), 0), 99.9),
    0.0,
    LEAST(COALESCE(SUM(course.total_credits), 0), 99.9),
    @test_user_id,
    NOW()
FROM iems_courses AS course
WHERE course.academic_batch_id = @academic_batch_id
  AND course.semester = @semester_number
  AND course.status = 1
  AND NOT EXISTS (
      SELECT 1
      FROM lms_academic_batch_semester_crs_structure AS existing
      WHERE existing.academic_batch_id = @academic_batch_id
        AND existing.semester_id = @semester_id
        AND existing.crs_type_id = course.course_type_id
  )
GROUP BY course.course_type_id;

COMMIT;

-- ---------------------------------------------------------------------------
-- 4. Edit test data: adjust dates and one course-type limit after seeding.
--    Set @run_edit to 1 only when you are ready to test the edit API.
-- ---------------------------------------------------------------------------
SET @run_edit := 0;
START TRANSACTION;

UPDATE iems_semester
SET
    enroll_end_date = DATE_ADD(CURDATE(), INTERVAL 14 DAY),
    enroll_end_time = '18:00:00',
    modified_by = @test_user_id,
    modify_date = NOW()
WHERE semester_id = @semester_id
  AND academic_batch_id = @academic_batch_id
  AND @run_edit = 1;

UPDATE lms_academic_batch_semester_crs_structure
SET
    stud_min_crs_enroll = 1.0,
    stud_max_crs_enroll = LEAST(crs_type_total, 6.0),
    modified_by = @test_user_id,
    modified_date = NOW()
WHERE academic_batch_id = @academic_batch_id
  AND semester_id = @semester_id
  AND @run_edit = 1
ORDER BY ctcs_id
LIMIT 1;

COMMIT;

-- ---------------------------------------------------------------------------
-- 5. Re-check results.
-- ---------------------------------------------------------------------------
SELECT
    semester.enroll_start_date,
    semester.enroll_start_time,
    semester.enroll_end_date,
    semester.enroll_end_time,
    semester.total_crs_enroll,
    semester.own_crclm_elective,
    semester.other_crclm_elective
FROM iems_semester AS semester
WHERE semester.semester_id = @semester_id;

SELECT
    course_type.course_type_desc,
    structure.crs_type_total,
    structure.stud_min_crs_enroll,
    structure.stud_max_crs_enroll
FROM lms_academic_batch_semester_crs_structure AS structure
JOIN iems_course_type AS course_type
    ON course_type.course_type_id = structure.crs_type_id
WHERE structure.academic_batch_id = @academic_batch_id
  AND structure.semester_id = @semester_id
ORDER BY course_type.course_type_desc;

-- Optional cleanup: do not run unless this batch/semester is dedicated to testing.
-- DELETE FROM lms_academic_batch_semester_crs_structure
-- WHERE academic_batch_id = @academic_batch_id AND semester_id = @semester_id;
