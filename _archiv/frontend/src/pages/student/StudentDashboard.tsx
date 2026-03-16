import { useQuery } from "@tanstack/react-query";
import { Text, Spinner, Select, makeStyles, tokens } from "@fluentui/react-components";
import { useState } from "react";
import { api } from "../../hooks/useApi";
import { useAuth } from "../../auth/AuthProvider";
import type { Class, StudentRecordResponse, Competency } from "../../types";
import IbKChecklist from "../../components/student/IbKChecklist";
import PbKRubricGrid from "../../components/student/PbKRubricGrid";
import GradeSummaryCard from "../../components/student/GradeSummaryCard";

const useStyles = makeStyles({
  root: { padding: tokens.spacingVerticalL, maxWidth: 900 },
  header: { marginBottom: tokens.spacingVerticalM },
  grid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: tokens.spacingHorizontalL },
});

export default function StudentDashboard() {
  const styles = useStyles();
  const { user } = useAuth();
  const [classId, setClassId] = useState<string>("");

  const { data: classes } = useQuery<Class[]>({
    queryKey: ["classes"],
    queryFn: () => api.get("/classes"),
    onSuccess: (data) => { if (data.length && !classId) setClassId(data[0].id); },
  } as any);

  const { data: records, isLoading } = useQuery<StudentRecordResponse>({
    queryKey: ["records", "me", classId],
    queryFn: () => api.get(`/records/me/${classId}`),
    enabled: !!classId,
  });

  const { data: competencies } = useQuery<Competency[]>({
    queryKey: ["competencies"],
    queryFn: () => api.get("/competencies"),
  });

  const ibk = competencies?.filter((c) => c.typ === "einfach") ?? [];
  const pbk = competencies?.filter((c) => c.typ === "niveau") ?? [];

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <Text size={700} weight="semibold">Meine Kompetenzen</Text>
        {classes && classes.length > 1 && (
          <Select value={classId} onChange={(_, d) => setClassId(d.value)}>
            {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        )}
      </div>

      {isLoading && <Spinner />}

      {records && (
        <>
          <GradeSummaryCard grade={records.grade} />
          <div className={styles.grid}>
            <IbKChecklist competencies={ibk} records={records.records} />
            <PbKRubricGrid competencies={pbk} records={records.records} />
          </div>
        </>
      )}
    </div>
  );
}
