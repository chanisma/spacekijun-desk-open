-- 데스크 메시지 — 내가 보낸 메시지를 서버에서 읽기 (2026-10-21 요청)
--
-- 전에는 보낸 메시지가 상대 알림함에만 있어 다시 읽을 수 없었고, 보낸 PC 에만 DPAPI 로 남겼다
-- → 다른 PC 에서는 대화에 내 말이 빠졌다. 보낸 메시지도 이미 notification_events 에 있으니
-- 보낸 사람 본인에게만 돌려주는 함수를 둔다. 새 표는 없다.
--   · 보낸 사람은 로그인 계정에서 서버가 정한다(desk_message_who) — 남의 보낸 메시지는 못 본다.
--   · 화면이 쓰는 칸만: id · 받는 사람(id·표시 이름) · 내용 · 시각 · 상대가 읽었는지.
-- 적용: Supabase 프로젝트 your-project-ref (apply_migration desk_message_sent). 이 파일은 기록용 사본.

-- 보낸 사람으로 찾기 — 이 함수와 send_desk_message 의 1시간 한도 세기가 같이 쓴다
create index if not exists notification_events_desk_message_sender_idx
  on public.notification_events ((meta->>'sender_resource_id'), created_at desc)
  where type = 'desk_message';

create or replace function public.desk_message_sent(p_limit int default 300)
returns jsonb
language plpgsql
stable
security definer
set search_path to 'public', 'pg_temp'
as $function$
declare
  v_me jsonb := public.desk_message_who(auth.uid());
  v_rows jsonb;
begin
  if v_me is null then
    raise exception '학생 또는 선생님으로 연결된 계정만 메시지를 볼 수 있습니다' using errcode = '42501';
  end if;
  select coalesce(jsonb_agg(jsonb_build_object(
           'id', s.id, 'to', s.resource_id, 'body', s.message, 'time', s.created_at, 'read', s.is_read,
           'to_label', case
             when r.type = 'student' and coalesce(r.meta->>'grade', '') <> '' and coalesce(r.meta->>'class', '') <> ''
               then format('%s학년 %s반 %s', r.meta->>'grade', r.meta->>'class',
                           case when coalesce(r.meta->>'number', '') <> '' then (r.meta->>'number') || '번 ' else '' end)
                    || r.name
             when r.type = 'student' then r.name
             when r.name is not null then r.name || ' 선생님'
             else '' end)
         order by s.created_at), '[]'::jsonb)
    into v_rows
  from (select n.id, n.resource_id, n.message, n.created_at, n.is_read
        from public.notification_events n
        where n.type = 'desk_message'
          and n.meta->>'sender_resource_id' = v_me->>'resource_id'
        order by n.created_at desc
        limit least(greatest(coalesce(p_limit, 300), 1), 500)) s
  left join public.resource r on r.id = s.resource_id;
  return v_rows;
end;
$function$;

revoke all on function public.desk_message_sent(int) from public, anon;
grant execute on function public.desk_message_sent(int) to authenticated;
