export default function AdvisoryTimeline({ items }) {
  return (
    <div className="timeline">
      {items.map((item, i) => (
        <div className="tl-item" key={item.id}>
          <div className="tl-left">
            <div className={`tl-dot ${item.dot_state}`} />
            {i < items.length - 1 && <div className="tl-line" />}
          </div>
          <div className="tl-content">
            <div className="tl-when">{item.when_label}</div>
            <div className="tl-action">{item.action}</div>
            <div className="tl-note">{item.note}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
