import { Text, tokens, makeStyles } from "@fluentui/react-components";
import type { Competency, Record } from "../../types";

const useStyles = makeStyles({
  root: {},
  title: { marginBottom: tokens.spacingVerticalS },
  row: { display: "grid", gridTemplateColumns: "1fr auto", gap: 8, alignItems: "center", padding: "4px 0", borderBottom: "1px solid #f0f0f0" },
  levels: { display: "flex", gap: 4 },
  cell: {
    width: 28, height: 28, display: "flex", alignItems: "center", justifyContent: "center",
    borderRadius: 4, border: "1px solid #ccc", fontSize: 12,
  },
  achieved: { backgroundColor: tokens.colorBrandBackground, color: "white", border: "none" },
});

interface Props {
  competencies: Competency[];
  records: Record[];
}

export default function PbKRubricGrid({ competencies, records }: Props) {
  const styles = useStyles();
  const recordMap = new Map(records.map((r) => [r.competency_id, r]));

  return (
    <div className={styles.root}>
      <Text size={500} weight="semibold" className={styles.title}>pBK (Prozessbezogene Kompetenzen)</Text>
      {competencies.map((c) => {
        const level = recordMap.get(c.id)?.niveau_level ?? -1;
        return (
          <div key={c.id} className={styles.row}>
            <Text size={200}>{c.name}</Text>
            <div className={styles.levels}>
              {[0, 1, 2, 3].map((n) => (
                <div
                  key={n}
                  className={`${styles.cell} ${n === level ? styles.achieved : ""}`}
                >
                  {n}
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
