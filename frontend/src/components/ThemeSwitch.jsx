import { Icon } from "../ui.jsx";

const OPTS = [["light", "sun", "Light"], ["dark", "moon", "Dark"], ["system", "monitor", "System"]];

export default function ThemeSwitch({ value, onChange }) {
  return (
    <div className="theme-switch" role="radiogroup" aria-label="Theme">
      {OPTS.map(([k, icon, label]) => (
        <button key={k} role="radio" aria-checked={value === k} title={`${label} theme`} onClick={() => onChange(k)}>
          <Icon name={icon} size={16} /><span className="sr">{label}</span>
        </button>
      ))}
    </div>
  );
}
