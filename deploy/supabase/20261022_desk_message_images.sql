-- 데스크 메시지 — 사진 (2026-10-22 요청, 교사판·학생판)
--
-- 붙여넣기·끌어 놓기로 메시지에 사진을 넣는다 (한 번에 4장, 한 장 1.5MB — 화면이 미리 줄여 보낸다).
--   · 사진은 desk_message_images 에 둔다. RLS 를 켜고 정책을 두지 않아 **표를 직접은 아무도 못 읽는다** —
--     보내기(send_desk_message_v2)·받기(desk_message_image) 함수로만. 받기는 보낸 사람·받는 사람만 된다.
--   · 서버에는 **7일만** 둔다 (cron desk-message-images-7d, 매시). 화면은 본 사진을 그 PC 의 캡처 보관함에
--     파일로 남기므로(core/desk_message.py) 7일이 지나도 본 사람에게는 남는다.
--   · 알림(notification_events)의 meta.images 에 [{id, w, h}] 만 적는다 — 알림 표에는 그림이 없다.
--   · 보내기는 send_desk_message_v2(사진 인자 p_images). 옛 앱(사진 모르는 판)이 부르는 3인자
--     send_desk_message 는 그 자리에서 v2 를 사진 없이 부르게 바꾼다 — 지우지 않는다(지우면 옛 앱이 끊긴다).
--     같은 이름에 인자만 더한 판을 따로 두면 PostgREST 가 어느 쪽인지 못 골라 둘 다 실패한다.
-- 적용: Supabase 프로젝트 your-project-ref (apply_migration desk_message_images). 이 파일은 기록용 사본.

create table if not exists public.desk_message_images (
  id uuid primary key,
  notification_id uuid not null references public.notification_events(id) on delete cascade,
  sender_resource_id uuid not null,
  recipient_resource_id uuid not null,
  mime text not null check (mime in ('image/jpeg', 'image/png', 'image/webp')),
  width int not null check (width between 1 and 8000),
  height int not null check (height between 1 and 8000),
  bytes int not null,
  data bytea not null,
  created_at timestamptz not null default now()
);
create index if not exists desk_message_images_created_idx on public.desk_message_images (created_at);
create index if not exists desk_message_images_sender_idx on public.desk_message_images (sender_resource_id, created_at);
create index if not exists desk_message_images_notification_idx on public.desk_message_images (notification_id);
alter table public.desk_message_images enable row level security;   -- 정책 없음 = 함수로만
revoke all on table public.desk_message_images from public, anon, authenticated;


-- 보내기 — 20261019 의 send_desk_message 에 p_images 를 더한 판. 사진만 보내면 글은 비워도 된다.
create or replace function public.send_desk_message_v2(p_recipient_resource_id uuid, p_body text,
                                                    p_reply_to_notification_id uuid default null,
                                                    p_images jsonb default null)
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
  v_count int := 0;
  v_item jsonb;
  v_data bytea;
  v_mime text;
  v_pics jsonb := '[]'::jsonb;
  v_rows jsonb := '[]'::jsonb;
  v_total bigint := 0;
  v_recent bigint;
  v_image_id uuid;
begin
  if v_uid is null then
    raise exception '로그인이 필요합니다' using errcode = '28000';
  end if;

  v_me := public.desk_message_who(v_uid);
  if v_me is null then
    raise exception '학생 또는 선생님으로 연결된 계정만 메시지를 보낼 수 있습니다' using errcode = '42501';
  end if;

  if p_images is not null and jsonb_typeof(p_images) <> 'null' then
    if jsonb_typeof(p_images) <> 'array' then
      raise exception '사진 형식이 올바르지 않습니다' using errcode = '22023';
    end if;
    v_count := jsonb_array_length(p_images);
  end if;
  if v_count > 4 then
    raise exception '사진은 한 번에 4장까지 보낼 수 있습니다' using errcode = '22023';
  end if;

  if v_body = '' and v_count = 0 then
    raise exception '메시지 내용이 비어 있습니다' using errcode = '22023';
  end if;
  if char_length(v_body) > 1000 then
    raise exception '메시지는 1000자까지 보낼 수 있습니다 (지금 %자)', char_length(v_body) using errcode = '22001';
  end if;

  select * into v_recipient
  from public.resource r
  where r.id = p_recipient_resource_id
    and coalesce(r.status, 'active') = 'active'
    and r.type = case when v_me->>'role' = 'student' then 'teacher' else 'student' end;
  if v_recipient.id is null then
    raise exception '받는 사람을 찾을 수 없습니다' using errcode = 'P0002';
  end if;

  v_limit := case when v_me->>'role' = 'student' then 30 else 200 end;
  select count(*) into v_sent
  from public.notification_events n
  where n.type = 'desk_message'
    and n.created_at > now() - interval '1 hour'
    and n.meta->>'sender_resource_id' = v_me->>'resource_id';
  if v_sent >= v_limit then
    raise exception '한 시간에 %건까지 보낼 수 있습니다. 잠시 뒤에 다시 보내 주세요', v_limit using errcode = '54000';
  end if;

  -- 사진: 형식(첫 바이트로 확인)·크기. 아직 넣지 않고 id 만 정해 둔다 — 알림 meta 에 함께 적으려고
  for v_item in select value from jsonb_array_elements(coalesce(p_images, '[]'::jsonb)) loop
    v_mime := v_item->>'mime';
    begin
      v_data := decode(coalesce(v_item->>'data', ''), 'base64');
    exception when others then
      raise exception '사진 파일이 올바르지 않습니다' using errcode = '22023';
    end;
    if octet_length(v_data) < 16 or octet_length(v_data) > 1572864 then
      raise exception '사진 한 장은 1.5MB 까지 보낼 수 있습니다' using errcode = '22023';
    end if;
    if not ((v_mime = 'image/jpeg' and substring(v_data from 1 for 3) = '\xffd8ff'::bytea)
         or (v_mime = 'image/png' and substring(v_data from 1 for 8) = '\x89504e470d0a1a0a'::bytea)
         or (v_mime = 'image/webp' and substring(v_data from 1 for 4) = '\x52494646'::bytea
             and substring(v_data from 9 for 4) = '\x57454250'::bytea)) then
      raise exception '사진은 JPEG·PNG·WebP 만 보낼 수 있습니다' using errcode = '22023';
    end if;
    if coalesce((v_item->>'width')::int, 0) not between 1 and 8000
       or coalesce((v_item->>'height')::int, 0) not between 1 and 8000 then
      raise exception '사진 크기가 올바르지 않습니다' using errcode = '22023';
    end if;
    v_total := v_total + octet_length(v_data);
    v_image_id := gen_random_uuid();
    v_pics := v_pics || jsonb_build_array(jsonb_build_object(
      'id', v_image_id, 'w', (v_item->>'width')::int, 'h', (v_item->>'height')::int));
    v_rows := v_rows || jsonb_build_array(jsonb_build_object('id', v_image_id, 'mime', v_mime,
      'width', (v_item->>'width')::int, 'height', (v_item->>'height')::int, 'data', v_item->>'data'));
  end loop;

  -- 사진 하루 한도 (학생 30MB, 교직원 150MB) — 서버에 7일 쌓이는 양을 묶는다
  if v_count > 0 then
    select coalesce(sum(i.bytes), 0) into v_recent
    from public.desk_message_images i
    where i.sender_resource_id = (v_me->>'resource_id')::uuid
      and i.created_at > now() - interval '1 day';
    if v_recent + v_total > (case when v_me->>'role' = 'student' then 31457280 else 157286400 end) then
      raise exception '오늘 보낼 수 있는 사진 양을 넘었습니다. 내일 다시 보내 주세요' using errcode = '54000';
    end if;
  end if;

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
  if v_count > 0 then
    v_meta := v_meta || jsonb_build_object('images', v_pics, 'photo_only', v_body = '');
  end if;
  if v_original_id is not null then
    v_meta := v_meta || jsonb_build_object('reply_to_notification_id', v_original_id,
                                           'quote', left(coalesce(v_original_message, ''), 300));
  end if;

  -- 사진만 보내면 알림 글은 '사진 N장' (스페이스기전 알림함에도 그렇게 보인다)
  insert into public.notification_events (resource_id, type, title, message, meta, priority)
  values (v_recipient.id, 'desk_message', '[메시지] ' || (v_me->>'label'),
          case when v_body = '' then format('사진 %s장', v_count) else v_body end, v_meta, 'medium')
  returning id into v_new_id;

  insert into public.desk_message_images (id, notification_id, sender_resource_id, recipient_resource_id,
                                          mime, width, height, bytes, data)
  select (r->>'id')::uuid, v_new_id, (v_me->>'resource_id')::uuid, v_recipient.id, r->>'mime',
         (r->>'width')::int, (r->>'height')::int, octet_length(decode(r->>'data', 'base64')), decode(r->>'data', 'base64')
  from jsonb_array_elements(v_rows) r;

  if v_original_id is not null then
    update public.notification_events
       set meta = coalesce(meta, '{}'::jsonb) || jsonb_build_object('replied_at', now()),
           is_read = true
     where id = v_original_id;
  end if;

  if v_recipient.type = 'student' then
    select exists (select 1 from public.profiles p
                   where p.role = 'student' and split_part(p.email, '@', 1) = v_recipient.meta->>'id')
      into v_linked;
  else
    select exists (select 1 from public.user_resource ur where ur.resource_id = v_recipient.id) into v_linked;
  end if;

  return jsonb_build_object('notification_id', v_new_id, 'recipient_resource_id', v_recipient.id,
                            'recipient_name', v_recipient.name, 'recipient_linked', v_linked,
                            'images', v_pics);
end;
$function$;

revoke all on function public.send_desk_message_v2(uuid, text, uuid, jsonb) from public, anon;
grant execute on function public.send_desk_message_v2(uuid, text, uuid, jsonb) to authenticated;

-- 옛 앱이 부르는 3인자 판 — 같은 규칙(v2)으로, 사진 없이
create or replace function public.send_desk_message(p_recipient_resource_id uuid, p_body text,
                                                    p_reply_to_notification_id uuid default null)
returns jsonb
language sql
security definer
set search_path to 'public', 'pg_temp'
as $function$
  select public.send_desk_message_v2(p_recipient_resource_id, p_body, p_reply_to_notification_id, null);
$function$;


-- 사진 한 장 받기 — 보낸 사람·받는 사람만. 7일이 지나 지워졌거나 남의 것이면 null (있는지 알려 주지 않는다)
create or replace function public.desk_message_image(p_image_id uuid)
returns jsonb
language plpgsql
stable
security definer
set search_path to 'public', 'pg_temp'
as $function$
declare
  v_me jsonb := public.desk_message_who(auth.uid());
  v_row public.desk_message_images%rowtype;
begin
  if v_me is null or p_image_id is null then
    return null;
  end if;
  select * into v_row from public.desk_message_images i where i.id = p_image_id;
  if v_row.id is null then
    return null;
  end if;
  if v_row.sender_resource_id::text <> v_me->>'resource_id'
     and not public.owns_notification_resource(v_row.recipient_resource_id) then
    return null;
  end if;
  return jsonb_build_object('id', v_row.id, 'mime', v_row.mime, 'width', v_row.width, 'height', v_row.height,
                            'created_at', v_row.created_at, 'data', encode(v_row.data, 'base64'));
end;
$function$;

revoke all on function public.desk_message_image(uuid) from public, anon;
grant execute on function public.desk_message_image(uuid) to authenticated;


-- 내가 보낸 메시지 — 20261021 에 사진(images·photo_only)을 더한다
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
           'images', coalesce(s.meta->'images', '[]'::jsonb), 'photo_only', coalesce((s.meta->>'photo_only')::boolean, false),
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
  from (select n.id, n.resource_id, n.message, n.created_at, n.is_read, n.meta
        from public.notification_events n
        where n.type = 'desk_message'
          and n.meta->>'sender_resource_id' = v_me->>'resource_id'
        order by n.created_at desc
        limit least(greatest(coalesce(p_limit, 300), 1), 500)) s
  left join public.resource r on r.id = s.resource_id;
  return v_rows;
end;
$function$;


-- 7일 지난 사진은 지운다 (매시 7분). 같은 이름이면 cron.schedule 이 고쳐 쓴다
select cron.schedule('desk-message-images-7d', '7 * * * *',
  $$delete from public.desk_message_images where created_at < now() - interval '7 days'$$);
