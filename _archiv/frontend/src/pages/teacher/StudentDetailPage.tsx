import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Text, Button, Spinner, tokens, makeStyles } from "@fluentui/react-components";
import { api } from "../../hooks/useApi";
import type { StudentRecordResponse, Competency } from "../../types";
import IbKTeacherPanel from "../../components/teacher/IbKTeacherPanel";
import PbKTeacherPanel from "../../components/teacher/PbKTeacherPanel";

const useStyles = makeStyles({
  root: { padding: tokens.spacingVerticalL, maxWidth: 900 },
  grid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: tokens.spacingHorizontalL, marginTop: tokens.spacingVerticalM },
});

export default function StudentDetailPage() {
  const { classId, studentId } = useParams<{ classId: string; studentId: string }>();
  const navigate = useNavigate();
  const styles = useStyles();

  const { data: records, isLoading } = useQuery<StudentRecordResponse>({
    queryKey: ["records", classId, studentId],
    queryFn: () => api.get(`/records/${classId}/${studentId}`),
  });

  const { data: competencies } = useQuery<Competency[]>({
    queryKey: ["competencies"],
    queryFn: () => api.get("/competencies"),
  });

  const ibk = competencies?.filter((c) => c.typ === "einfach") ?? [];
  const pbk = competencies?.filter((c) => c.typ === "niveau") ?? [];

  return (
    <div className={styles.root}>
      <Button appearance="subtle" onClick={() => navigate(`/teacher/classes/${classId}`)}>← Zurück</Button>
      <Text size={700} weight="semibold" block>Schüler:in bearbeiten</Text>

      {records && (
        <Text block>
          Note: <strong>{records.grade.note}</strong> ({records.grade.prozent}% · {records.grade.gesamtpunkte}/{records.grade.max_punkte} Punkte)
        </Text>
      )}

      {isLoading && <Spinner />}

      {records && classId && studentId && (
        <div className={styles.grid}>
          <IbKTeacherPanel
            competencies={ibk}
            records={records.records}
            classId={classId}
            studentId={studentId}
          />
          <PbKTeacherPanel
            competencies={pbk}
            records={records.records}
            classId={classId}
            studentId={studentId}
          />
        </div>
      )}
    </div>
  );
}
