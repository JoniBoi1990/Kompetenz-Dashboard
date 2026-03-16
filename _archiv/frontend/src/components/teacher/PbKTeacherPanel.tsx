import { Text, Input, tokens, makeStyles } from "@fluentui/react-components";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../hooks/useApi";
import type { Competency, Record } from "../../types";

const useStyles = makeStyles({
  root: {},
  row: { display: "grid", gridTemplateColumns: "1fr auto auto", gap: 8, alignItems: "center", padding: "4px 0", borderBottom: "1px solid #f0f0f0" },
  levels: { display: "flex", gap: 4 },
  cell: {
    width: 32, height: 32, display: "flex", alignItems: "center", justifyContent: "center",
    borderRadius: 4, border: "1px solid #ccc", fontSize: 13, cursor: "pointer",
    userSelect: "none",
  },
  active: { backgroundColor: tokens.colorBrandBackground, color: "white", border: "none" },
});

interface Props {
  competencies: Competency[];
  records: Record[];
  classId: string;
  studentId: string;
}

export default function PbKTeacherPanel({ competencies, records, classId, studentId }: Props) {
  const styles = useStyles();
  const queryClient = useQueryClient();
  const recordMap = new Map(records.map((r) => [r.competency_id, r]));

  const mutation = useMutation({
    mutationFn: ({ competencyId, niveau_level, evidence_url }: { competencyId: string; niveau_level: number; evidence_url?: string }) =>
      api.put(`/records/${classId}/${studentId}/${competencyId}`, { niveau_level, evidence_url }),
    onMutate: async ({ competencyId, niveau_level }) => {
      await queryClient.cancelQueries({ queryKey: ["records", classId, studentId] });
      const prev = queryClient.getQueryData(["records", classId, studentId]);
      queryClient.setQueryData(["records", classId, studentId], (old: any) => ({
        ...old,
        records: old?.records?.map((r: Record) =>
          r.competency_id === competencyId ? { ...r, niveau_level } : r
        ) ?? [],
      }));
      return { prev };
    },
    onError: (_err, _vars, context: any) => {
      if (context?.prev) queryClient.setQueryData(["records", classId, studentId], context.prev);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["records", classId, studentId] }),
  });

  return (
    <div className={styles.root}>
      <Text size={500} weight="semibold">pBK</Text>
      {competencies.map((c) => {
        const record = recordMap.get(c.id);
        const level = record?.niveau_level ?? -1;
        return (
          <div key={c.id} className={styles.row}>
            <Text size={200}>{c.name}</Text>
            <div className={styles.levels}>
              {[0, 1, 2, 3].map((n) => (
                <div
                  key={n}
                  className={`${styles.cell} ${n === level ? styles.active : ""}`}
                  onClick={() => mutation.mutate({ competencyId: c.id, niveau_level: n, evidence_url: record?.evidence_url ?? undefined })}
                  title={`Niveau ${n}`}
                >
                  {n}
                </div>
              ))}
            </div>
            <Input
              size="small"
              placeholder="Nachweis-URL"
              defaultValue={record?.evidence_url ?? ""}
              onBlur={(e) => {
                if (e.target.value !== (record?.evidence_url ?? "")) {
                  mutation.mutate({ competencyId: c.id, niveau_level: level >= 0 ? level : 0, evidence_url: e.target.value });
                }
              }}
              style={{ width: 160 }}
            />
          </div>
        );
      })}
    </div>
  );
}
