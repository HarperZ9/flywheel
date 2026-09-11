[Code]
var
  FwSources, FwDests, FwPrints, FwNames, FwVersions: array of String;
  FwInventories, FwSourceRels, FwDestRels, FwDispositions: array of String;
  FwQuarantineDir, FwRollbackStatus, FwRollbackDetail: String;
  FwMoved, FwInstallFinished: Boolean;
  FwMovedCount: Integer;

#include "flywheel_metadata_receipt.iss"

function FwExists(Path: String): Boolean;
begin
  Result := DirExists(Path) or FileExists(Path);
end;

function FwIsReparse(FileName: String): Boolean;
var Rec: TFindRec;
begin
  Result := False;
  if FindFirst(FileName, Rec) then begin
    Result := Rec.Attributes and FILE_ATTRIBUTE_REPARSE_POINT <> 0; FindClose(Rec);
  end;
end;

function FwPlainDir(Path: String; Code: String; var Failure: String): Boolean;
begin
  Result := True;
  if DirExists(Path) then if FwIsReparse(Path) then begin
    Failure := Code + ': ' + Path; Result := False;
  end;
end;

function FwNormalize(Value: String): String;
var I: Integer; Ch: String;
begin
  Result := ''; Value := LowerCase(Trim(Value));
  for I := 1 to Length(Value) do begin
    Ch := Copy(Value, I, 1); if (Ch = '_') or (Ch = '.') then Ch := '-';
    Result := Result + Ch;
  end;
end;

function FwEnds(Value: String; Suffix: String): Boolean;
begin
  Result := (Length(Value) >= Length(Suffix)) and
    (Copy(Value, Length(Value) - Length(Suffix) + 1, Length(Suffix)) = Suffix);
end;

function FwMetadataDir(Name: String): Boolean;
var Lower: String;
begin
  Lower := LowerCase(Name); Result := FwEnds(Lower, '.dist-info') or FwEnds(Lower, '.egg-info');
end;

function FwHeader(Text: String; Header: String): String;
var Line: String; Prefix: String; Index: Integer;
begin
  Result := ''; Prefix := LowerCase(Header) + ':';
  while Text <> '' do begin
    Index := Pos(#10, Text);
    if Index = 0 then begin Line := Text; Text := ''; end
    else begin Line := Copy(Text, 1, Index - 1); Delete(Text, 1, Index); end;
    Line := Trim(Line);
    if LowerCase(Copy(Line, 1, Length(Prefix))) = Prefix then begin
      Result := Trim(Copy(Line, Length(Prefix) + 1, Length(Line))); exit;
    end;
  end;
end;

function FwLoadMeta(Dir: String; var Name: String; var Version: String): Boolean;
var Text: AnsiString;
begin
  Result := False; Name := ''; Version := '';
  if LoadStringFromFile(PathCombine(Dir, 'METADATA'), Text) or
     LoadStringFromFile(PathCombine(Dir, 'PKG-INFO'), Text) then begin
    Name := FwHeader(Text, 'Name'); Version := FwHeader(Text, 'Version'); Result := Name <> '';
  end;
end;

function FwAllowedFile(Relative: String): Boolean;
var Lower: String; LicenseName: String;
begin
  Lower := LowerCase(Relative);
  Result := (Lower = 'metadata') or (Lower = 'pkg-info') or (Lower = 'entry_points.txt') or
    (Lower = 'top_level.txt') or (Lower = 'requires.txt') or (Lower = 'sources.txt') or
    (Lower = 'record') or (Lower = 'wheel') or (Lower = 'installer') or
    (Lower = 'requested') or (Lower = 'direct_url.json') or
    (Lower = 'dependency_links.txt') or (Lower = 'namespace_packages.txt') or
    (Copy(Lower, 1, 7) = 'license') or (Copy(Lower, 1, 6) = 'notice');
  if not Result and (Copy(Lower, 1, 9) = 'licenses\') then begin
    LicenseName := Copy(Lower, 10, Length(Lower));
    Result := (Pos('\', LicenseName) = 0) and ((Copy(LicenseName, 1, 7) = 'license') or
      (Copy(LicenseName, 1, 6) = 'notice') or (Copy(LicenseName, 1, 7) = 'copying'));
  end;
end;

function FwChild(Relative: String; Name: String): String;
begin
  if Relative = '' then Result := Name else Result := Relative + '\' + Name;
end;

function FwValidateTree(Dir: String; Relative: String; var Failure: String): Boolean;
var Rec: TFindRec; Child: String; Rel: String;
begin
  Result := True;
  if FindFirst(PathCombine(Dir, '*'), Rec) then begin
    try
      repeat
        if (Rec.Name <> '.') and (Rec.Name <> '..') then begin
          Child := PathCombine(Dir, Rec.Name); Rel := FwChild(Relative, Rec.Name);
          if Rec.Attributes and FILE_ATTRIBUTE_REPARSE_POINT <> 0 then begin
            Failure := 'REPARSE_METADATA_ROOT: ' + Child; Result := False; exit;
          end;
          if Rec.Attributes and FILE_ATTRIBUTE_DIRECTORY <> 0 then begin
            if Rel <> 'licenses' then begin Failure := 'UNRECOGNIZED_METADATA_DIR: ' + Rel; Result := False; exit; end;
            if not FwValidateTree(Child, Rel, Failure) then begin Result := False; exit; end;
          end else if not FwAllowedFile(Rel) then begin
            Failure := 'UNRECOGNIZED_METADATA_FILE: ' + Rel; Result := False; exit;
          end;
        end;
      until not FindNext(Rec);
    finally
      FindClose(Rec);
    end;
  end;
end;

function FwInventory(Dir: String; Relative: String; var Failure: String; var Fingerprint: String): String;
var Rec: TFindRec; Child: String; Rel: String; Hash: String; Size: Int64; Item: String;
begin
  Result := '';
  if FindFirst(PathCombine(Dir, '*'), Rec) then begin
    try
      repeat
        if (Rec.Name <> '.') and (Rec.Name <> '..') then begin
          Child := PathCombine(Dir, Rec.Name); Rel := FwChild(Relative, Rec.Name);
          if Rec.Attributes and FILE_ATTRIBUTE_DIRECTORY <> 0 then Item := FwInventory(Child, Rel, Failure, Fingerprint)
          else begin
            if not FileExists(Child) then begin Failure := 'SOURCE_DRIFT: ' + Child; exit; end;
            if not FileSize64(Child, Size) then begin Failure := 'SOURCE_DRIFT: ' + Child; exit; end;
            Hash := GetSHA256OfFile(Child); Fingerprint := Fingerprint + LowerCase(FwSlash(Rel)) + '=' + Hash + ':' + IntToStr(Size) + #10;
            Item := '{"path":"' + FwEscape(FwSlash(Rel)) + '","size":' + IntToStr(Size) + ',"sha256":"' + Hash + '"}';
          end;
          if Item <> '' then begin if Result <> '' then Result := Result + ','; Result := Result + Item; end;
        end;
      until not FindNext(Rec);
    finally
      FindClose(Rec);
    end;
  end;
end;

procedure FwAdd(Source: String; Dest: String; Name: String; Version: String; Print: String; Inventory: String; RootName: String);
var I: Integer; QuarantineLeaf: String;
begin
  I := GetArrayLength(FwSources);
  SetArrayLength(FwSources, I + 1); SetArrayLength(FwDests, I + 1); SetArrayLength(FwPrints, I + 1);
  SetArrayLength(FwNames, I + 1); SetArrayLength(FwVersions, I + 1); SetArrayLength(FwInventories, I + 1);
  SetArrayLength(FwSourceRels, I + 1); SetArrayLength(FwDestRels, I + 1); SetArrayLength(FwDispositions, I + 1);
  QuarantineLeaf := ExtractFileName(FwQuarantineDir);
  FwSources[I] := Source; FwDests[I] := Dest; FwPrints[I] := Print; FwNames[I] := Name;
  FwVersions[I] := Version; FwInventories[I] := Inventory;
  FwSourceRels[I] := 'engine/_internal/' + RootName;
  FwDestRels[I] := 'FlywheelMetadataQuarantine/' + QuarantineLeaf + '/engine/_internal/' + RootName;
  FwDispositions[I] := 'not_attempted';
end;

function FwCollect(InternalRoot: String; var Failure: String): Boolean;
var Rec: TFindRec; Source: String; Dest: String; Name: String; Version: String; Print: String; Inventory: String;
begin
  Result := True;
  SetArrayLength(FwSources, 0); SetArrayLength(FwDests, 0); SetArrayLength(FwPrints, 0);
  SetArrayLength(FwNames, 0); SetArrayLength(FwVersions, 0); SetArrayLength(FwInventories, 0);
  SetArrayLength(FwSourceRels, 0); SetArrayLength(FwDestRels, 0); SetArrayLength(FwDispositions, 0);
  if not DirExists(InternalRoot) then exit;
  if FindFirst(PathCombine(InternalRoot, '*'), Rec) then begin
    try
      repeat
        if (Rec.Attributes and FILE_ATTRIBUTE_DIRECTORY <> 0) and (Rec.Name <> '.') and (Rec.Name <> '..') and FwMetadataDir(Rec.Name) then begin
          Source := PathCombine(InternalRoot, Rec.Name);
          if Rec.Attributes and FILE_ATTRIBUTE_REPARSE_POINT <> 0 then begin Failure := 'REPARSE_METADATA_ROOT: ' + Source; Result := False; exit; end;
          if not FwLoadMeta(Source, Name, Version) then begin Failure := 'MISSING_METADATA_BINDING: ' + Source; Result := False; exit; end;
          if FwNormalize(Name) <> 'flywheel-verify' then continue;
          if Version = '' then begin Failure := 'MISSING_METADATA_VERSION: ' + Source; Result := False; exit; end;
          if not FwValidateTree(Source, '', Failure) then begin Result := False; exit; end;
          Print := ''; Inventory := FwInventory(Source, '', Failure, Print);
          if Failure <> '' then begin Result := False; exit; end;
          Dest := PathCombine(PathCombine(FwQuarantineDir, 'engine\_internal'), Rec.Name);
          if FwExists(Dest) then begin Failure := 'QUARANTINE_COLLISION: ' + Dest; Result := False; exit; end;
          FwAdd(Source, Dest, FwNormalize(Name), Version, Print, Inventory, Rec.Name);
        end;
      until not FindNext(Rec);
    finally
      FindClose(Rec);
    end;
  end;
end;

procedure FwRollback(Detail: String);
var I: Integer; Failure: String; Parent: String; Print: String; Inv: String;
begin
  FwRollbackStatus := 'restored'; FwRollbackDetail := Detail;
  for I := FwMovedCount - 1 downto 0 do begin
    Parent := ExtractFileDir(FwSources[I]); Failure := '';
    if not DirExists(FwDests[I]) then Failure := 'ROLLBACK_MISSING_QUARANTINE'
    else if FwIsReparse(FwDests[I]) then Failure := 'ROLLBACK_REPARSE_QUARANTINE'
    else if not FwPlainDir(Parent, 'ROLLBACK_REPARSE_PARENT', Failure) then Failure := Failure
    else if not FwPlainDir(ExtractFileDir(Parent), 'ROLLBACK_REPARSE_ANCESTOR', Failure) then Failure := Failure
    else if FwExists(FwSources[I]) then Failure := 'ROLLBACK_SOURCE_EXISTS'
    else if not RenameFile(FwDests[I], FwSources[I]) then Failure := 'ROLLBACK_RENAME_FAILED'
    else begin
      Print := ''; Inv := FwInventory(FwSources[I], '', Failure, Print);
      if (Failure = '') and (Print <> FwPrints[I]) then Failure := 'ROLLBACK_FINGERPRINT_MISMATCH';
    end;
    if Failure <> '' then begin
      FwDispositions[I] := 'unresolved_conflict'; FwRollbackStatus := 'unresolved_conflict'; FwRollbackDetail := Failure;
    end else
      FwDispositions[I] := 'restored';
  end;
end;

function FwQuarantine(var Failure: String): Boolean;
var I: Integer; Print: String; Inv: String;
begin
  Result := True; FwMovedCount := 0;
  if GetArrayLength(FwSources) = 0 then exit;
  if not ForceDirectories(PathCombine(FwQuarantineDir, 'engine\_internal')) then begin Failure := 'QUARANTINE_CREATE_FAILED'; Result := False; exit; end;
  if not FwPlainDir(FwQuarantineDir, 'REPARSE_QUARANTINE_RUN', Failure) then begin Result := False; exit; end;
  if not FwPlainDir(PathCombine(FwQuarantineDir, 'engine'), 'REPARSE_QUARANTINE_ENGINE', Failure) then begin Result := False; exit; end;
  if not FwPlainDir(PathCombine(PathCombine(FwQuarantineDir, 'engine'), '_internal'), 'REPARSE_QUARANTINE_INTERNAL', Failure) then begin Result := False; exit; end;
  for I := 0 to GetArrayLength(FwSources) - 1 do begin
#ifdef FlywheelMetadataCleanupRaceProbe
    if I = 0 then SaveStringToFile(PathCombine(FwSources[I], 'entry_points.txt'), 'changed after precheck', False);
#endif
    Print := ''; Inv := FwInventory(FwSources[I], '', Failure, Print);
    if (Failure <> '') or (Print <> FwPrints[I]) then begin Failure := 'SOURCE_DRIFT: ' + FwSources[I]; if FwMovedCount > 0 then FwRollback(Failure); if FwMovedCount > 0 then FwReceipt('repair_required', Failure); Result := False; exit; end;
    if not FwPlainDir(ExtractFileDir(FwDests[I]), 'REPARSE_QUARANTINE_DEST_PARENT', Failure) then begin if FwMovedCount > 0 then FwRollback(Failure); if FwMovedCount > 0 then FwReceipt('repair_required', Failure); Result := False; exit; end;
    if not RenameFile(FwSources[I], FwDests[I]) then begin Failure := 'QUARANTINE_RENAME_FAILED: ' + FwSources[I]; if FwMovedCount > 0 then FwRollback(Failure); if FwMovedCount > 0 then FwReceipt('repair_required', Failure); Result := False; exit; end;
    FwMoved := True; FwDispositions[I] := 'quarantined'; FwMovedCount := FwMovedCount + 1;
#ifdef FlywheelMetadataCleanupPostMoveProbe
    if I = 0 then SaveStringToFile(PathCombine(FwDests[I], 'entry_points.txt'), 'changed after move', False);
#endif
    Print := ''; Inv := FwInventory(FwDests[I], '', Failure, Print);
    if (Failure <> '') or (Print <> FwPrints[I]) then begin Failure := 'SOURCE_DRIFT: ' + FwSources[I]; FwRollback(Failure); FwReceipt('repair_required', Failure); Result := False; exit; end;
  end;
#ifdef FlywheelMetadataCleanupAbortAfterQuarantine
  Failure := 'ABORT_AFTER_QUARANTINE'; FwRollback(Failure); FwReceipt('repair_required', Failure); Result := False; exit;
#endif
  FwReceipt('quarantined_before_payload', 'moved=' + IntToStr(GetArrayLength(FwSources)));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var AppRoot: String; InternalRoot: String; ParentRoot: String; Failure: String;
begin
  Result := ''; Failure := ''; FwRollbackStatus := ''; FwRollbackDetail := ''; AppRoot := ExpandConstant('{app}');
  InternalRoot := PathCombine(PathCombine(AppRoot, 'engine'), '_internal'); ParentRoot := ExtractFileDir(AppRoot);
#ifdef FlywheelMetadataCleanupQuarantineLeaf
  FwQuarantineDir := PathCombine(ParentRoot, 'FlywheelMetadataQuarantine\{#FlywheelMetadataCleanupQuarantineLeaf}');
#else
  FwQuarantineDir := PathCombine(ParentRoot, 'FlywheelMetadataQuarantine\metadata-{#AppVersion}-' + GetDateTimeString('yyyymmddhhnnss', '-', ':'));
#endif
  if not FwPlainDir(ParentRoot, 'REPARSE_PARENT_ROOT', Failure) then begin Result := Failure; exit; end;
  if not FwPlainDir(AppRoot, 'REPARSE_APP_ROOT', Failure) then begin Result := Failure; exit; end;
  if not FwPlainDir(PathCombine(AppRoot, 'engine'), 'REPARSE_ENGINE_ROOT', Failure) then begin Result := Failure; exit; end;
  if not FwPlainDir(InternalRoot, 'REPARSE_INTERNAL_ROOT', Failure) then begin Result := Failure; exit; end;
  if not FwPlainDir(ExtractFileDir(FwQuarantineDir), 'REPARSE_QUARANTINE_ROOT', Failure) then begin Result := Failure; exit; end;
  if not FwCollect(InternalRoot, Failure) then begin Result := Failure; exit; end;
  if not FwQuarantine(Failure) then Result := Failure;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then FwInstallFinished := True;
end;

procedure DeinitializeSetup();
begin
  if FwMoved and not FwInstallFinished and (FwRollbackStatus = '') then begin
    FwRollback('setup ended before new metadata payload finished installing');
    FwReceipt('repair_required', 'setup ended before new metadata payload finished installing');
  end;
end;
