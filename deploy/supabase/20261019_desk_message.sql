-- 데스크 메시지 — 학생 ↔ 선생님 (2026-10-19 요청, 스페이스기전 데스크 교사판·학생판)
--
-- 내용은 스페이스기전 알림(notification_events, type 'desk_message')으로만 오간다. 새 표는 없다.
--   · 받은 메시지 읽기·읽음 표시는 기존 RLS(owns_notification_resource)로 — 본인 알림만 보인다.
--   · 보내기는 이 함수로만: 보낸 사람은 로그인 계정에서 서버가 정한다(화면이 꾸밀 수 없다).
--   · 학생 → 재직 중인 선생님, 선생님 → 재학 중인 학생만. 학생끼리·선생님끼리는 막는다 (일단 학생-교사만).
--   · 학생 1시간 30건, 교직원 1시간 200건, 한 번에 1000자.
-- 적용: Supabase 프로젝트 your-project-ref (apply_migration desk_message). 이 파일은 기록용 사본.

-- 나는 누구인가 — 메시지에서 쓰는 보낸 사람 정보. 직접 부르지 못하게 권한을 거둔다(아래 revoke).
create or replace function public.desk_message_who(p_uid uuid)
returns jsonb
language plpgsql
stable
security definer
set search_path to 'public', 'pg_temp'
as $function$
declare
  v_id uuid;
  v_name text;
  v_meta jsonb;
  v_code text;
  v_count int;
begin
  if p_uid is null then
    return null;
  end if;

  -- 교직원: 내 계정에 연결된 교직원 리소스 (교사 우선 → 이름순, send_notification_reply 와 같은 규칙)
  if public.is_staff_teacher_or_admin(p_uid) then
    select r.id, r.name into v_id, v_name
    from public.user_resource ur
    join public.resource r on r.id = ur.resource_id
    where ur.user_id = p_uid and r.type in ('teacher', 'staff')
    order by (r.type = 'teacher') desc, r.name
    limit 1;
    if v_id is null then
      return null;
    end if;
    return jsonb_build_object('resource_id', v_id, 'name', v_name, 'role', 'teacher',
                              'label', v_name || ' 선생님');
  end if;

  -- 학생: 이메일 앞부분(학번 코드)으로 재학 중인 학생 리소스 (owns_notification_resource 와 같은 규칙)
  select split_part(p.email, '@', 1) into v_code
  from public.profiles p
  where p.id = p_uid and p.role = 'student';
  if v_code is null or v_code = '' then
    return null;
  end if;
  select count(*) into v_count
  from public.resource r
  where r.type = 'student' and coalesce(r.status, 'active') = 'active' and r.meta->>'id' = v_code;
  if v_count <> 1 then
    return null;                    -- 없거나 둘 이상이면 누구인지 단정하지 않는다
  end if;
  select r.id, r.name, r.meta into v_id, v_name, v_meta
  from public.resource r
  where r.type = 'student' and coalesce(r.status, 'active') = 'active' and r.meta->>'id' = v_code;
  return jsonb_build_object(
    'resource_id', v_id, 'name', v_name, 'role', 'student',
    'label', case when coalesce(v_meta->>'grade', '') <> '' and coalesce(v_meta->>'class', '') <> ''
                  then format('%s학년 %s반 %s', v_meta->>'grade', v_meta->>'class',
                              case when coalesce(v_meta->>'number', '') <> '' then (v_meta->>'number') || '번 ' else '' end)
                       || v_name
                  else v_name end);
end;
$function$;

revoke all on function public.desk_message_who(uuid) from public, anon, authenticated;


-- 메시지 보내기 — 받는 사람 알림함에 desk_message 알림 한 건. 답장이면 원래 메시지를 인용하고 '답장함' 표시.
create or replace function public.send_desk_message(p_recipient_resource_id uuid, p_body text,
                                                    p_reply_to_notification_id uuid default null)
returns jsonb
language plpgsql
security definer
set search_path to 'public', 'pg_temp'
as $function$
declare
  v_uid uuid := auth.uid();
  v_me jsonb;
  v_body text := btrim(coalesce(p_body, ''));
  v_recipient public.resource%rowtype;
  v_sent int;
  v_limit int;
  v_original_id uuid;
  v_original_message text;
  v_meta jsonb;
  v_new_id uuid;
  v_linked boolean;
begin
  -- auth.uid() 가 NULL 이면 아래 비교가 NULL 이 되어 가드를 통과한다 → 맨 앞에서 끊는다
  if v_uid is null then
    raise exception '로그인이 필요합니다' using errcode = '28000';
  end if;

  v_me := public.desk_message_who(v_uid);
  if v_me is null then
    raise exception '학생 또는 선생님으로 연결된 계정만 메시지를 보낼 수 있습니다' using errcode = '42501';
  end if;

  if v_body = '' then
    raise exception '메시지 내용이 비어 있습니다' using errcode = '22023';
  end if;
  if char_length(v_body) > 1000 then
    raise exception '메시지는 1000자까지 보낼 수 있습니다 (지금 %자)', char_length(v_body) using errcode = '22001';
  end if;

  -- 받는 사람: 학생은 재직 중인 선생님에게만, 선생님은 재학 중인 학생에게만 (일단 학생-교사만)
  select * into v_recipient
  from public.resource r
  where r.id = p_recipient_resource_id
    and coalesce(r.status, 'active') = 'active'
    and r.type = case when v_me->>'role' = 'student' then 'teacher' else 'student' end;
  if v_recipient.id is null then
    raise exception '받는 사람을 찾을 수 없습니다' using errcode = 'P0002';
  end if;

  -- 너무 많이 보내지 않게 (학생 1시간 30건, 교직원 200건)
  v_limit := case when v_me->>'role' = 'student' then 30 else 200 end;
  select count(*) into v_sent
  from public.notification_events n
  where n.type = 'desk_message'
    and n.created_at > now() - interval '1 hour'
    and n.meta->>'sender_resource_id' = v_me->>'resource_id';
  if v_sent >= v_limit then
    raise exception '한 시간에 %건까지 보낼 수 있습니다. 잠시 뒤에 다시 보내 주세요', v_limit using errcode = '54000';
  end if;

  -- 답장 대상: **내 알림일 때만** 인용한다. 남의 알림 id 면 조용히 생략 (있는지 알려 주지 않게)
  if p_reply_to_notification_id is not null then
    select n.id, n.message into v_original_id, v_original_message
    from public.notification_events n
    where n.id = p_reply_to_notification_id
      and public.owns_notification_resource(n.resource_id);
  end if;

  v_meta := jsonb_build_object(
    'source', 'spacekijun_desk',
    'sender_resource_id', v_me->>'resource_id',
    'sender_name', v_me->>'name',
    'sender_role', v_me->>'role',
    'sender_label', v_me->>'label');
  if v_original_id is not null then
    v_meta := v_meta || jsonb_build_object('reply_to_notification_id', v_original_id,
                                           'quote', left(coalesce(v_original_message, ''), 300));
  end if;

  insert into public.notification_events (resource_id, type, title, message, meta, priority)
  values (v_recipient.id, 'desk_message', '[메시지] ' || (v_me->>'label'), v_body, v_meta, 'medium')
  returning id into v_new_id;

  if v_original_id is not null then
    update public.notification_events
       set meta = coalesce(meta, '{}'::jsonb) || jsonb_build_object('replied_at', now()),
           is_read = true
     where id = v_original_id;
  end if;

  -- 받는 사람이 스페이스기전에 한 번도 들어오지 않았으면 알림은 저장되지만 아직 아무도 못 본다 → 화면이 말해 준다
  if v_recipient.type = 'student' then
    select exists (select 1 from public.profiles p
                   where p.role = 'student' and split_part(p.email, '@', 1) = v_recipient.meta->>'id')
      into v_linked;
  else
    select exists (select 1 from public.user_resource ur where ur.resource_id = v_recipient.id) into v_linked;
  end if;

  return jsonb_build_object('notification_id', v_new_id, 'recipient_resource_id', v_recipient.id,
                            'recipient_name', v_recipient.name, 'recipient_linked', v_linked);
end;
$function$;

revoke all on function public.send_desk_message(uuid, text, uuid) from public, anon;
grant execute on function public.send_desk_message(uuid, text, uuid) to authenticated;


-- 보낼 수 있는 사람 목록 — 학생에게는 재직 중인 선생님(이름), 선생님에게는 재학 중인 학생(학년·반·번호·이름).
-- 화면이 resource 를 통째로 읽지 않게 필요한 칸만 돌려준다.
create or replace function public.desk_message_directory()
returns jsonb
language plpgsql
stable
security definer
set search_path to 'public', 'pg_temp'
as $function$
declare
  v_me jsonb := public.desk_message_who(auth.uid());
  v_people jsonb;
begin
  if v_me is null then
    raise exception '학생 또는 선생님으로 연결된 계정만 메시지를 보낼 수 있습니다' using errcode = '42501';
  end if;
  if v_me->>'role' = 'student' then
    select coalesce(jsonb_agg(jsonb_build_object('id', r.id, 'name', r.name) order by r.name), '[]'::jsonb)
      into v_people
    from public.resource r
    where r.type = 'teacher' and coalesce(r.status, 'active') = 'active';
  else
    select coalesce(jsonb_agg(jsonb_build_object(
             'id', r.id, 'name', r.name, 'grade', r.meta->>'grade', 'class', r.meta->>'class',
             'number', r.meta->>'number')
           order by (r.meta->>'grade'), lpad(coalesce(r.meta->>'class', ''), 3, '0'),
                    lpad(coalesce(r.meta->>'number', ''), 3, '0'), r.name), '[]'::jsonb)
      into v_people
    from public.resource r
    where r.type = 'student' and coalesce(r.status, 'active') = 'active'
      and coalesce(r.meta->>'test_account', '') <> 'true';     -- 시험용 계정은 목록에서 뺀다
  end if;
  return jsonb_build_object('role', v_me->>'role', 'me', v_me->>'label', 'people', v_people);
end;
$function$;

revoke all on function public.desk_message_directory() from public, anon;
grant execute on function public.desk_message_directory() to authenticated;
