function FwEscape(Value: String): String;
begin
  Result := Value; StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True); StringChangeEx(Result, #13, '\r', True);
  StringChangeEx(Result, #10, '\n', True);
end;

function FwSlash(Value: String): String;
begin
  Result := Value; StringChangeEx(Result, '\', '/', True);
end;

function FwCode(Value: String): String;
var Index: Integer;
begin
  Index := Pos(':', Value);
  if Index = 0 then Result := Value else Result := Copy(Value, 1, Index - 1);
end;

function FwMetadataRootsJson(): String;
var I: Integer;
begin
  Result := '';
  for I := 0 to GetArrayLength(FwSources) - 1 do begin
    if Result <> '' then Result := Result + ','#13#10;
    Result := Result + '    {"source_root":"' + FwEscape(FwSourceRels[I]) + '",' +
      '"quarantine_root":"' + FwEscape(FwDestRels[I]) + '",' +
      '"disposition":"' + FwEscape(FwDispositions[I]) + '",' +
      '"name":"' + FwEscape(FwNames[I]) + '",' +
      '"version":"' + FwEscape(FwVersions[I]) + '",' +
      '"fingerprint_sha256":"' + GetSHA256OfUnicodeString(FwPrints[I]) + '",' +
      '"children":[' + FwInventories[I] + ']}';
  end;
end;

procedure FwReceipt(Status: String; Detail: String);
var Text: String; RollStatus: String;
begin
  if FwQuarantineDir = '' then exit;
  ForceDirectories(FwQuarantineDir);
  RollStatus := FwRollbackStatus; if RollStatus = '' then RollStatus := 'not_needed';
  Text := '{'#13#10 + '  "schema": "flywheel.installer-metadata-quarantine/v1",'#13#10 +
    '  "status": "' + FwEscape(Status) + '",'#13#10 +
    '  "detail": "' + FwEscape(FwCode(Detail)) + '",'#13#10 +
    '  "candidate": {"app_version":"{#AppVersion}","metadata_root":"engine/_internal/flywheel_verify.egg-info"},'#13#10 +
    '  "rollback": {"status":"' + FwEscape(RollStatus) + '","detail":"' + FwEscape(FwCode(FwRollbackDetail)) + '"},'#13#10 +
    '  "metadata_roots": ['#13#10 + FwMetadataRootsJson() + #13#10 + '  ]'#13#10 + '}'#13#10;
  SaveStringToFile(PathCombine(FwQuarantineDir, 'metadata-quarantine-receipt.json'), Text, False);
  if Status = 'repair_required' then
    SaveStringToFile(PathCombine(FwQuarantineDir, 'repair-required.json'), Text, False);
end;
