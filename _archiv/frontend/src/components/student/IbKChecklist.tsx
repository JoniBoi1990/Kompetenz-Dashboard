import { Checkbox, Text, tokens, makeStyles } from "@fluentui/react-components";
import type { Competency, Record } from "../../types";

const useStyles = makeStyles({
  root: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXS },
  title: { marginBottom: tokens.spacingVerticalS },
});

interface Props {
  competencies: Competency[];
  records: Record[];
}

export default function IbKChecklist({ competencies, records }: Props) {
  const styles = useStyles();
  const recordMap = new Map(records.map((r) => [r.competency_id, r]));

  return (
    <div className={styles.root}>
      <Text size={500} weight="semibold" className={styles.title}>ibK (Inhaltsbezogene Kompetenzen)</Text>
      {competencies.map((c) => (
        <Checkbox
          key={c.id}
          label={c.name}
          checked={recordMap.get(c.id)?.achieved ?? false}
          disabled
        />
      ))}
    </div>
  );
}
