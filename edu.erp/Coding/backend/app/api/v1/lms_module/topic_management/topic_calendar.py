"""Calendar links use verified existing tables absent from the shared ORM models."""
from sqlalchemy import text

def delivery_slots(db, context):
    return [dict(row) for row in db.execute(text('''
        SELECT d.class_date, t.class_start_time AS start_time, t.class_end_time AS end_time
        FROM lms_tt_time_table_day_mapping d
        JOIN lms_tt_time_table t ON t.time_table_id=d.time_table_id
        JOIN lms_tt_time_table_details td ON td.tt_detail_id=d.tt_detail_id
        WHERE td.academic_batch_id=:batch AND td.semester_id=:semester
          AND td.section_id=:section AND COALESCE(d.allot_crs_id,t.crs_id)=:course
        ORDER BY d.class_date,t.class_start_time
    '''), dict(batch=context.academic_batch_id, semester=context.semester_id,
              section=context.section_id, course=context.course_id)).mappings()]

def sync_calendar(db, mapping, portion, user_id, extra=False):
    params = dict(batch=mapping.academic_batch_id, semester=mapping.semester_id,
        course=mapping.crs_id, section=mapping.section_id, topic=mapping.topic_id,
        portion=portion.portion_id, source=portion.lesson_schedule_id, user=user_id,
        date=portion.delivery_date or (portion.planned_date if extra else None),
        start=str(portion.start_time) if portion.start_time else None,
        end=str(portion.end_time) if portion.end_time else None,
        lecture=portion.portion_ref, content=portion.portion_per_hour,
        status=2 if portion.delivery_date else 1)
    if not params['date'] and portion.planned_date and not portion.delivery_date:
        planned_link = db.execute(text('''SELECT 1 FROM lms_lesson_schedule l
            JOIN lms_ls_lesson_schedule_map lm ON lm.lls_id=l.lls_id
            WHERE lm.mtp_id=:portion AND l.completion_date IS NULL LIMIT 1'''), params).scalar()
        if planned_link:
            params['date'] = portion.planned_date
    old_ids = list(db.execute(text('SELECT lls_id FROM lms_ls_lesson_schedule_map WHERE mtp_id=:portion'), params).scalars())
    db.execute(text('DELETE FROM lms_ls_lesson_schedule_map WHERE mtp_id=:portion'), params)
    for old_id in old_ids:
        db.execute(text('UPDATE lms_lesson_schedule SET status=1 WHERE lls_id=:id AND NOT EXISTS (SELECT 1 FROM lms_ls_lesson_schedule_map WHERE lls_id=:id)'), {'id': old_id})
    if not params['date'] or not params['start'] or not params['end']:
        return
    lesson_id = db.execute(text('''SELECT lls_id FROM lms_lesson_schedule
        WHERE academic_batch_id=:batch AND semester_id=:semester AND crs_id=:course
          AND section_id=:section AND plan_date=:date AND substr(start_time,1,5)=substr(:start,1,5) AND substr(end_time,1,5)=substr(:end,1,5)
        ORDER BY lls_id LIMIT 1'''), params).scalar()
    if not lesson_id:
        result = db.execute(text('''INSERT INTO lms_lesson_schedule
            (academic_batch_id,semester_id,crs_id,section_id,topic_id,plan_date,completion_date,
             start_time,end_time,status,portion_ref,portion_per_hour,created_by,modified_by)
            VALUES (:batch,:semester,:course,:section,:topic,:date,:completion,
             :start,:end,:status,:lecture,:content,:user,:user)'''), {**params, 'completion': portion.delivery_date})
        lesson_id = result.lastrowid
    else:
        db.execute(text('UPDATE lms_lesson_schedule SET status=CASE WHEN :completion IS NOT NULL THEN 2 ELSE status END,completion_date=COALESCE(:completion,completion_date),modified_by=:user WHERE lls_id=:id'),
            {**params, 'id': lesson_id, 'completion': portion.delivery_date})
    params['lesson'] = lesson_id
    db.execute(text('''INSERT INTO lms_ls_lesson_schedule_map
        (lls_id,lesson_schedule_id,mtp_id,created_by,modified_by)
        VALUES (:lesson,:source,:portion,:user,:user)'''), params)
    db.execute(text('''INSERT INTO lms_ls_topic_map (lls_id,topic_id,created_by,modified_by)
        SELECT :lesson,:topic,:user,:user WHERE NOT EXISTS
        (SELECT 1 FROM lms_ls_topic_map WHERE lls_id=:lesson AND topic_id=:topic)'''), params)
    # Student IDs and USNs come from iems_students; course/batch membership is explicit.
    db.execute(text('''INSERT INTO lms_ls_student_map (lls_id,ssd_id,student_usn,created_by,modified_by)
        SELECT DISTINCT :lesson,s.student_id,s.usno,:user,:user
        FROM iems_students s JOIN cudos_map_courseto_student cs ON cs.student_id=s.student_id
        WHERE s.status=1 AND cs.academic_batch_id=:batch AND cs.semester_id=:semester
          AND cs.crs_id=:course AND (cs.section_id=:section OR cs.batch_id=:section)
          AND NOT EXISTS (SELECT 1 FROM lms_ls_student_map sm
                          WHERE sm.lls_id=:lesson AND sm.ssd_id=s.student_id)'''), params)
