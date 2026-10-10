function export_author_damping_holdout(outputRoot)
%EXPORT_AUTHOR_DAMPING_HOLDOUT Generate actual author models, never interpolate.
    arguments
        outputRoot (1,1) string = ""
    end
    projectRoot = fileparts(fileparts(fileparts(mfilename('fullpath'))));
    authorRoot = fullfile(projectRoot, 'external', 'cifelli-small-gain-phase');
    simplusRoot = fullfile(projectRoot, 'external', 'simplus-grid-tool');
    if strlength(outputRoot) == 0
        outputRoot = fullfile(projectRoot, 'results', 'automatic-transform-search', 'new-operating-points-01');
    end
    assert(~isfolder(outputRoot), 'TransformHoldout:ExistingOutput', 'Output already exists.');
    runtimeParent = fullfile(projectRoot, 'tmp', 'transform-holdout-20261003');
    runtimeRoot = fullfile(runtimeParent, 'runtime-simplus-grid-tool');
    assert(~isfolder(runtimeParent), 'TransformHoldout:ExistingRuntime', 'Runtime already exists.');
    oldPath = path;
    oldFolder = pwd;
    oldVisibility = get(groot, 'defaultFigureVisible');
    oldFigures = findall(groot, 'Type', 'figure');
    cleanup = onCleanup(@() restoreEnvironment(oldPath, oldFolder, oldVisibility, ...
        oldFigures, runtimeParent, projectRoot));
    [ok, message] = copyfile(simplusRoot, runtimeRoot);
    assert(ok, 'TransformHoldout:CopyFailure', '%s', message);
    [ok, message] = copyfile(fullfile(authorRoot, 'GridFormingVSI.m'), ...
        fullfile(runtimeRoot, '+SimplusGT', '+Class', 'GridFormingVSI.m'), 'f');
    assert(ok, 'TransformHoldout:CopyFailure', '%s', message);
    [ok, message] = copyfile(fullfile(authorRoot, 'UserData_inf_bus_Fig_8.xlsm'), ...
        fullfile(runtimeRoot, 'UserData.xlsm'), 'f');
    assert(ok, 'TransformHoldout:CopyFailure', '%s', message);
    if isfile(fullfile(runtimeRoot, 'UserData.json'))
        delete(fullfile(runtimeRoot, 'UserData.json'));
    end
    addpath(genpath(runtimeRoot), '-begin');
    set(groot, 'defaultFigureVisible', 'off');
    cd(runtimeRoot);
    rehash;
    assert(strcmpi(which('SimplusGT.Class.GridFormingVSI'), ...
        fullfile(runtimeRoot, '+SimplusGT', '+Class', 'GridFormingVSI.m')), ...
        'TransformHoldout:WrongClass', 'Author overlay class was not resolved.');
    UserDataName = 'UserData'; %#ok<NASGU>
    UserDataType = 1; %#ok<NASGU>
    NumApparatus = NaN;
    ApparatusType = {};
    ApparatusBus = {};
    ApparatusPowerFlow = {};
    Para = {};
    ObjGmCell = {};
    SimplusGT.Toolbox.Main();
    assert(NumApparatus == 2 && ApparatusType{2} == 20 && abs(Para{2}.Dw - .05) < 1e-12, ...
        'TransformHoldout:WrongBaseline', 'Unexpected author input.');
    [~, networkMatrix] = ObjYbusDss.GetDSS(ObjYbusDss);
    networkMatrix = networkMatrix(3:end, 3:end);
    frequencies = logspace(-3, 4, 1000);
    networkResponse = freqresp(networkMatrix, 2*pi*frequencies);
    damping = [.05, .1, .2, .35, .5];
    recordCells = cell(1, numel(damping));
    startTime = tic;
    for index = 1:numel(damping)
        assert(toc(startTime) < 120, 'TransformHoldout:Budget', 'Model generation budget exceeded.');
        parameters = Para{2};
        parameters.Dw = damping(index);
        [converterObject, converterDss] = SimplusGT.Toolbox.ApparatusModelCreate( ...
            ApparatusBus{2}, ApparatusType{2}, ApparatusPowerFlow{2}, ...
            parameters, Ts, ListBusNew, Advance);
        objects = ObjGmCell;
        objects{2} = converterObject;
        linked = SimplusGT.Toolbox.ApparatusModelLink(objects);
        [closedObject, closedDss] = SimplusGT.Toolbox.ConnectGmZbus(linked, ObjZbusDss, NumBus);
        assert(isproper(closedDss), 'TransformHoldout:Improper', 'Closed model must be proper.');
        closedSsObject = SimplusGT.ObjDss2Ss(closedObject);
        [~, closedSs] = closedSsObject.GetSS(closedSsObject);
        poles = eig(closedSs.A);
        dynamicPoles = poles(abs(poles) > 2*pi*1e-7);
        converterMatrix = minreal(converterDss(1:2, 1:2));
        returnZeros = tzero(ss(minreal(networkMatrix + converterMatrix)));
        dynamicZeros = returnZeros(abs(returnZeros) > 2*pi*1e-7);
        [~, dominantIndex] = max(real(dynamicPoles));
        mismatch = min(abs(dynamicZeros - dynamicPoles(dominantIndex)));
        assert(mismatch < 1e-7, 'TransformHoldout:PoleZeroMismatch', 'Port and connected model mismatch.');
        record = struct('damping', damping(index), ...
            'frequencies_hz', frequencies, ...
            'converter', responseData(freqresp(converterMatrix, 2*pi*frequencies)), ...
            'network', responseData(networkResponse), ...
            'closed_loop_poles_per_second', [real(dynamicPoles), imag(dynamicPoles)], ...
            'return_zeros_per_second', [real(dynamicZeros), imag(dynamicZeros)], ...
            'dominant_real_per_second', max(real(dynamicPoles)), ...
            'dominant_oscillation_hz', abs(imag(dynamicPoles(dominantIndex)))/(2*pi), ...
            'dominant_pole_zero_difference_per_second', mismatch);
        recordCells{index} = record;
        fprintf('GFM_HOLDOUT_MODEL D=%.3g dominant_real=%.12g /s mismatch=%.3g /s\n', ...
            damping(index), record.dominant_real_per_second, mismatch);
    end
    fixtureManifest = jsondecode(fileread(fullfile(projectRoot, 'experiments', 'baseline', ...
        'fixtures', 'author_fig8_fixture_manifest.json')));
    records = [recordCells{:}];
    result = struct('status', 'complete', 'matlab_release', version('-release'), ...
        'source', 'author GridFormingVSI and Simplus, recreated per Para.Dw', ...
        'generation_elapsed_seconds', toc(startTime), ...
        'power_flow', ApparatusPowerFlow{2}, 'base_angular_frequency', Wbase, ...
        'fixture_operating_point', fixtureManifest.derivedOperatingPoint, 'cases', records);
    assert(norm(ApparatusPowerFlow{2}(:) - [-.5; 0; 1; 0; Wbase]) < 1e-10, ...
        'TransformHoldout:OperatingPoint', 'Author operating point changed.');
    mkdir(outputRoot);
    outputFile = fullfile(outputRoot, 'models.json');
    writelines(jsonencode(result), outputFile);
    reread = jsondecode(fileread(outputFile));
    assert(strcmp(reread.status, 'complete') && numel(reread.cases) == 5, ...
        'TransformHoldout:Readback', 'Output readback failed.');
    fprintf('GFM_HOLDOUT_EXPORT_COMPLETE %s\n', outputFile);
end

function result = responseData(response)
    result = struct();
    for row = 1:2
        for column = 1:2
            values = squeeze(response(row, column, :));
            result.(sprintf('m%d%d_real', row, column)) = real(values);
            result.(sprintf('m%d%d_imag', row, column)) = imag(values);
        end
    end
end

function restoreEnvironment(oldPath, oldFolder, oldVisibility, oldFigures, runtimeParent, projectRoot)
    path(oldPath);
    cd(oldFolder);
    set(groot, 'defaultFigureVisible', oldVisibility);
    newFigures = setdiff(findall(groot, 'Type', 'figure'), oldFigures);
    delete(newFigures);
    absoluteTarget = char(java.io.File(runtimeParent).getCanonicalPath());
    intendedParent = char(java.io.File(fullfile(projectRoot, 'tmp')).getCanonicalPath());
    assert(startsWith(lower(absoluteTarget), lower([intendedParent, filesep])), ...
        'TransformHoldout:UnsafeCleanup', 'Runtime cleanup escapes project tmp.');
    if isfolder(absoluteTarget)
        rmdir(absoluteTarget, 's');
    end
end
