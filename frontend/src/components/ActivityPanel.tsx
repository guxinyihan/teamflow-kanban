import { formatDistanceToNow } from 'date-fns';
import type { Activity } from '../types';
export function ActivityPanel({ events }: { events: Activity[] }) {
  return (
    <ol className="activity-list">
      {events.length === 0 ? (
        <li className="muted">No recorded activity yet.</li>
      ) : (
        events.map((event) => {
          const from = event.details?.source_column_name || event.details?.from_column;
          const to = event.details?.target_column_name || event.details?.to_column;
          const title = event.details?.title || event.details?.name;
          const assignee = event.details?.assignee_name;
          const wip = event.details?.wip_limit;
          return (
            <li key={event.id}>
              <div>
                <strong>{event.actor_name}</strong> {event.action.replace(/[_.]/g, ' ')}
              </div>
              <p>
                {typeof title === 'string' ? title : `${event.entity_type} #${event.entity_id}`}
              </p>
              {typeof assignee === 'string' ? <p>Assignee: {assignee}</p> : null}
              {typeof wip === 'number' || wip === null ? (
                <p>WIP limit: {wip === null ? 'Unlimited' : wip}</p>
              ) : null}
              {typeof event.details?.label === 'string' ? (
                <p>Label: {event.details.label}</p>
              ) : null}
              {typeof event.details?.filename === 'string' ? (
                <p>File: {event.details.filename}</p>
              ) : null}
              {typeof from === 'string' && typeof to === 'string' ? (
                <p>
                  {from} → {to}
                </p>
              ) : null}
              <time dateTime={event.created_at}>
                {formatDistanceToNow(new Date(event.created_at), { addSuffix: true })}
              </time>
            </li>
          );
        })
      )}
    </ol>
  );
}
