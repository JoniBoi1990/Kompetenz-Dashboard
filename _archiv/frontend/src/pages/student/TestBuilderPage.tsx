import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  Text, Button, Checkbox, Accordion, AccordionItem,
  AccordionHeader, AccordionPanel, Spinner, tokens, makeStyles,
} from "@fluentui/react-components";
import { api } from "../../hooks/useApi";
import type { Class, Competency, QuestionItem, GeneratedTest, StudentRecordResponse } from "../../types";

const useStyles = makeStyles({
  root: { padding: tokens.spacingVerticalL, maxWidth: 800 },
  actions: { marginTop: tokens.spacingVerticalM, display: "flex", gap: tokens.spacingHorizontalS },
});

export default function TestBuilderPage() {
  const styles = useStyles();
  const [classId, setClassId] = useState<string>("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [preview, setPreview] = useState<QuestionItem[] | null>(null);

  const { data: classes } = useQuery<Class[]>({
    queryKey: ["classes"],
    queryFn: () => api.get("/classes"),
    onSuccess: (data: Class[]) => { if (data.length && !classId) setClassId(data[0].id); },
  } as any);

  const { data: competencies } = useQuery<Competency[]>({
    queryKey: ["competencies"],
    queryFn: () => api.get("/competencies"),
  });

  const { data: records } = useQuery<StudentRecordResponse>({
    queryKey: ["records", "me", classId],
    queryFn: () => api.get(`/records/me/${classId}`),
    enabled: !!classId,
  });

  const achievedIds = new Set(
    records?.records
      .filter((r) => r.achieved || (r.niveau_level ?? 0) >= 3)
      .map((r) => r.competency_id) ?? []
  );

  const missing = competencies?.filter((c) => !achievedIds.has(c.id)) ?? [];

  const previewMutation = useMutation({
    mutationFn: () =>
      api.post<{ questions: QuestionItem[] }>("/tests/preview", {
        class_id: classId,
        competency_ids: Array.from(selected),
      }),
    onSuccess: (data) => setPreview(data.questions),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      api.post<GeneratedTest>("/tests", {
        class_id: classId,
        questions: preview,
      }),
    onSuccess: () => {
      alert("Test wird generiert! Du findest ihn unter 'Meine Tests'.");
      setPreview(null);
      setSelected(new Set());
    },
  });

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  return (
    <div className={styles.root}>
      <Text size={700} weight="semibold">Test erstellen</Text>
      <Text block>Wähle die Kompetenzen, die du üben möchtest:</Text>

      {missing.map((c) => (
        <Checkbox
          key={c.id}
          label={c.name}
          checked={selected.has(c.id)}
          onChange={() => toggle(c.id)}
        />
      ))}

      <div className={styles.actions}>
        <Button
          appearance="primary"
          disabled={selected.size === 0 || previewMutation.isPending}
          onClick={() => previewMutation.mutate()}
        >
          Vorschau
        </Button>
      </div>

      {preview && (
        <>
          <Text size={600} weight="semibold" block style={{ marginTop: 16 }}>
            Vorschau ({preview.length} Fragen)
          </Text>
          <Accordion multiple>
            {preview.map((q, i) => (
              <AccordionItem key={q.kid} value={q.kid}>
                <AccordionHeader>Frage {i + 1}</AccordionHeader>
                <AccordionPanel>
                  <Text>[{q.kid}] {q.text}</Text>
                </AccordionPanel>
              </AccordionItem>
            ))}
          </Accordion>
          <div className={styles.actions}>
            <Button
              appearance="primary"
              onClick={() => createMutation.mutate()}
              disabled={createMutation.isPending}
            >
              {createMutation.isPending ? <Spinner size="tiny" /> : "PDF generieren"}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
