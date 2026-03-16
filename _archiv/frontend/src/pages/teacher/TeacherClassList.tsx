import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Text, Button, Input, tokens, makeStyles, Card, CardHeader } from "@fluentui/react-components";
import { useNavigate } from "react-router-dom";
import { api } from "../../hooks/useApi";
import type { Class } from "../../types";

const useStyles = makeStyles({
  root: { padding: tokens.spacingVerticalL, maxWidth: 700 },
  form: { display: "flex", gap: tokens.spacingHorizontalS, marginBottom: tokens.spacingVerticalM },
  grid: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalS },
});

export default function TeacherClassList() {
  const styles = useStyles();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [year, setYear] = useState("2025/26");

  const { data: classes } = useQuery<Class[]>({
    queryKey: ["classes"],
    queryFn: () => api.get("/classes"),
  });

  const createMutation = useMutation({
    mutationFn: () => api.post("/classes", { name, school_year: year }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["classes"] });
      setName("");
    },
  });

  return (
    <div className={styles.root}>
      <Text size={700} weight="semibold">Meine Klassen</Text>

      <div className={styles.form}>
        <Input placeholder="Klassenname (z.B. 9a Chemie)" value={name} onChange={(_, d) => setName(d.value)} />
        <Input placeholder="Schuljahr" value={year} onChange={(_, d) => setYear(d.value)} style={{ width: 120 }} />
        <Button appearance="primary" onClick={() => createMutation.mutate()} disabled={!name}>
          Erstellen
        </Button>
      </div>

      <div className={styles.grid}>
        {classes?.map((c) => (
          <Card key={c.id} onClick={() => navigate(`/teacher/classes/${c.id}`)} style={{ cursor: "pointer" }}>
            <CardHeader header={<Text weight="semibold">{c.name}</Text>} description={c.school_year} />
          </Card>
        ))}
      </div>
    </div>
  );
}
