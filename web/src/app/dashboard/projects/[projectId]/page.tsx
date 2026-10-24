{generatedVersions.length > 0 ? (
          <Card className="mt-5">
            <CardHeader>
              <CardTitle>Generated exports</CardTitle>
              <CardDescription>{generatedVersions.length} retained output version(s). The two newest unprotected versions are kept automatically; protected versions remain until you delete them.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {generatedVersions.map((output) => (
                <section key={output.id} className="rounded-xl border border-border p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="font-semibold">Version {output.version}</h3>
                      <p className="mt-1 text-xs text-muted-foreground">Generated {output.createdAt.toLocaleString("en-IN")}</p>
                      {output.isProtected && <p className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-primary"><ShieldCheck className="size-3.5" /> Protected from automatic deletion</p>}
                    </div>
                    <ProjectVersionActions projectId={project.id} versionId={output.id} versionNumber={output.version} initialProtected={output.isProtected} />
                  </div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    {output.stepFilePath && <a href={`/api/projects/${project.id}/files/step?versionId=${encodeURIComponent(output.id)}`} className="flex items-center gap-3 rounded-xl border border-border p-3 hover:border-primary/50"><Download className="size-5 text-primary" /><span><span className="block font-semibold">STEP file</span><span className="mt-1 block text-xs text-muted-foreground">CAD interchange format</span></span></a>}
                    {output.stlFilePath && <a href={`/api/projects/${project.id}/files/stl?versionId=${encodeURIComponent(output.id)}`} className="flex items-center gap-3 rounded-xl border border-border p-3 hover:border-primary/50"><Download className="size-5 text-primary" /><span><span className="block font-semibold">STL file</span><span className="mt-1 block text-xs text-muted-foreground">3D printing mesh</span></span></a>}
                  </div>
                </section>
              ))}
            </CardContent>
          </Card>
        ) : project.status === "FAILED" ? (
          <Card className="mt-5 border-destructive/30"><CardHeader><CardTitle className="text-destructive">Generation failed</CardTitle><CardDescription>No successful export was stored. Review the description or check the deployment&apos;s CAD service logs.</CardDescription></CardHeader><CardContent><Button asChild><Link href="/dashboard/projects/new">Try again</Link></Button></CardContent></Card>
        ) : (
          <Card className="mt-5"><CardHeader><CardTitle>Project files</CardTitle><CardDescription>This project has not generated CAD exports yet.</CardDescription></CardHeader><CardContent><div className="flex items-start gap-3 text-sm leading-6 text-muted-foreground"><FileText className="mt-1 size-5 shrink-0" /> Upload a source drawing and use the OCR panel above to extract and review its text. CAD generation remains limited to supported, fully dimensioned descriptions.</div></CardContent></Card>
        )}
      </div>
    </main>
  );
}
