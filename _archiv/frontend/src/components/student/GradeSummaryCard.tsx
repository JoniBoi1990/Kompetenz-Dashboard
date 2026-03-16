import { Text, Card, tokens, makeStyles, Badge } from "@fluentui/react-components";
import type { GradeSummary } from "../../types";

const useStyles = makeStyles({
  card: { marginBottom: tokens.spacingVerticalM, padding: tokens.spacingVerticalM },
  row: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalM },
  noteBadge: { fontSize: 24, padding: "8px 16px" },
});

const noteColor = (note: string): "brand" | "success" | "warning" | "danger" | "informative" => {
  if (note === "1") return "success";
  if (note === "2") return "success";
  if (note === "3") return "informative";
  if (note === "4") return "warning";
  return "danger";
};

interface Props {
  grade: GradeSummary;
}

export default function GradeSummaryCard({ grade }: Props) {
  const styles = useStyles();
  return (
    <Card className={styles.card}>
      <div className={styles.row}>
        <Badge color={noteColor(grade.note)} size="extra-large" className={styles.noteBadge}>
          Note {grade.note}
        </Badge>
        <div>
          <Text size={500}>{grade.prozent}%</Text>
          <Text block size={200} style={{ color: tokens.colorNeutralForeground3 }}>
            {grade.gesamtpunkte} / {grade.max_punkte} Punkte
          </Text>
        </div>
      </div>
    </Card>
  );
}
