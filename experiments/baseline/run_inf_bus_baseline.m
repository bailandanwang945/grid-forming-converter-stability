function summary = run_inf_bus_baseline(caseName)
%RUN_INF_BUS_BASELINE Reproduce the author's infinite-bus baseline in isolation.
%   SUMMARY = RUN_INF_BUS_BASELINE("stable") uses UserData_inf_bus.xlsm.
%   SUMMARY = RUN_INF_BUS_BASELINE("unstable") uses
%   UserData_inf_bus_Fig_8.xlsm. The Simplus snapshot is copied to a
%   disposable runtime directory so that the author's GridFormingVSI class
%   can be overlaid without modifying either third-party source tree.

    arguments
        caseName (1, 1) string {mustBeMember(caseName, ["stable", "unstable"])}
    end

    projectRoot = fileparts(fileparts(fileparts(mfilename('fullpath'))));
    authorRoot = fullfile(projectRoot, 'external', 'cifelli-small-gain-phase');
    simplusRoot = fullfile(projectRoot, 'external', 'simplus-grid-tool');
    outputRoot = fullfile(projectRoot, 'results', 'baseline', caseName);
    runtimeRoot = fullfile(projectRoot, 'tmp', 'baseline', caseName, ...
        'runtime-simplus-grid-tool');

    if caseName == "stable"
        inputName = 'UserData_inf_bus.xlsm';
    else
        inputName = 'UserData_inf_bus_Fig_8.xlsm';
    end

    oldPath = path;
    oldFolder = pwd;
    oldFigureVisibility = get(groot, 'defaultFigureVisible');
    cleanup = onCleanup(@() restoreEnvironment( ...
        oldPath, oldFolder, oldFigureVisibility, runtimeRoot)); %#ok<NASGU>

    prepareRuntimeTool(simplusRoot, authorRoot, runtimeRoot, inputName);
    path(oldPath);
    rmpathIfPresent(genpath(simplusRoot));
    addpath(genpath(runtimeRoot), '-begin');
    addpath(authorRoot, '-begin');
    addpath(fullfile(projectRoot, 'src'), '-begin');
    set(groot, 'defaultFigureVisible', 'off');
    cd(runtimeRoot);
    rehash;

    resolvedClass = which('SimplusGT.Class.GridFormingVSI');
    expectedClass = fullfile(runtimeRoot, '+SimplusGT', '+Class', 'GridFormingVSI.m');
    assert(strcmpi(resolvedClass, expectedClass), ...
        'Baseline:WrongClass', 'The isolated author class was not resolved.');

    UserDataName = 'UserData'; %#ok<NASGU>
    UserDataType = 1; %#ok<NASGU>
    GmDssCell = []; %#ok<NASGU>
    ObjYbusDss = []; %#ok<NASGU>
    GsysSs = []; %#ok<NASGU>
    SimplusGT.Toolbox.Main();

    Yc = minreal(GmDssCell{2}(1:2, 1:2));
    [~, Ynet] = ObjYbusDss.GetDSS(ObjYbusDss);
    Ynet = Ynet(3:end, 3:end);

    frequenciesHz = logspace(log10(1e-3), log10(1e4), 1000).';
    angularFrequency = 2*pi*frequenciesHz;
    authorSectorial = false(size(frequenciesHz));
    for index = 1:numel(frequenciesHz)
        matrix = evalfr(Yc, 1i*angularFrequency(index));
        authorSectorial(index) = check_sectoriality(matrix);
    end

    firstSectorialIndex = find(authorSectorial, 1, 'first');
    if isempty(firstSectorialIndex)
        firstSectorialHz = NaN;
    else
        firstSectorialHz = frequenciesHz(firstSectorialIndex);
    end

    localFrequenciesHz = linspace(0.6, 1.2, 121).';
    lowerBound = zeros(size(localFrequenciesHz));
    upperBound = zeros(size(localFrequenciesHz));
    normalizedMargin = zeros(size(localFrequenciesHz));
    classification = strings(size(localFrequenciesHz));
    classifierOptions = struct( ...
        'NumAngles', 1440, 'RelTol', 1e-10, 'AbsTol', 0, 'Refine', true);
    for index = 1:numel(localFrequenciesHz)
        matrix = evalfr(Yc, 1i*2*pi*localFrequenciesHz(index));
        result = classifyNumericalRange(matrix, classifierOptions);
        lowerBound(index) = result.normalizedLowerBound;
        upperBound(index) = result.normalizedUpperBound;
        normalizedMargin(index) = result.normalizedMargin;
        classification(index) = result.classification;
    end

    firstPositiveIndex = find(normalizedMargin > 0, 1, 'first');
    if isempty(firstPositiveIndex) || firstPositiveIndex == 1
        interpolatedBoundaryHz = NaN;
    else
        indices = firstPositiveIndex + [-1, 0];
        interpolatedBoundaryHz = interp1( ...
            normalizedMargin(indices), localFrequenciesHz(indices), 0);
    end

    polesHz = eig(GsysSs.A)/(2*pi);
    [maximumRealPoleHz, maximumRealPoleIndex] = max(real(polesHz));
    dominantPoleHz = polesHz(maximumRealPoleIndex);

    if ~isfolder(outputRoot)
        mkdir(outputRoot);
    end
    frequencyTable = table( ...
        frequenciesHz, authorSectorial, ...
        'VariableNames', {'frequency_Hz', 'author_sectorial'});
    localTable = table( ...
        localFrequenciesHz, normalizedMargin, lowerBound, upperBound, classification, ...
        'VariableNames', {'frequency_Hz', 'normalized_margin', ...
        'normalized_lower_bound', 'normalized_upper_bound', 'classification'});
    writetable(frequencyTable, fullfile(outputRoot, 'author_sectoriality.csv'));
    writetable(localTable, fullfile(outputRoot, 'bounded_sectoriality_0p6_1p2Hz.csv'));

    summary = struct( ...
        'caseName', caseName, ...
        'matlabVersion', string(version), ...
        'matlabRelease', string(version('-release')), ...
        'resolvedGridFormingVSI', string(resolvedClass), ...
        'inputWorkbook', string(fullfile(authorRoot, inputName)), ...
        'firstAuthorSectorialHz', firstSectorialHz, ...
        'interpolatedMarginBoundaryHz', interpolatedBoundaryHz, ...
        'maximumRealPoleHz', maximumRealPoleHz, ...
        'dominantPoleHzReal', real(dominantPoleHz), ...
        'dominantPoleHzImag', imag(dominantPoleHz), ...
        'isClosedLoopStable', maximumRealPoleHz <= 1e-4);
    writelines(jsonencode(summary, PrettyPrint=true), ...
        fullfile(outputRoot, 'summary.json'));
    save(fullfile(outputRoot, 'baseline_workspace.mat'), ...
        'Yc', 'Ynet', 'GsysSs', 'summary');

    fprintf('BASELINE case=%s first_author_sectorial_Hz=%.9g ', caseName, firstSectorialHz);
    fprintf('bounded_margin_boundary_Hz=%.9g max_real_pole_Hz=%.9g\n', ...
        interpolatedBoundaryHz, maximumRealPoleHz);
end

function prepareRuntimeTool(simplusRoot, authorRoot, runtimeRoot, inputName)
    if isfolder(runtimeRoot)
        rmdir(runtimeRoot, 's');
    end
    [copyStatus, copyMessage] = copyfile(simplusRoot, runtimeRoot);
    assert(copyStatus, 'Baseline:CopySimplusFailed', '%s', copyMessage);
    authorClass = fullfile(authorRoot, 'GridFormingVSI.m');
    runtimeClass = fullfile(runtimeRoot, '+SimplusGT', '+Class', 'GridFormingVSI.m');
    [copyStatus, copyMessage] = copyfile(authorClass, runtimeClass, 'f');
    assert(copyStatus, 'Baseline:CopyClassFailed', '%s', copyMessage);
    [copyStatus, copyMessage] = copyfile( ...
        fullfile(authorRoot, inputName), fullfile(runtimeRoot, 'UserData.xlsm'), 'f');
    assert(copyStatus, 'Baseline:CopyInputFailed', '%s', copyMessage);
    jsonPath = fullfile(runtimeRoot, 'UserData.json');
    if isfile(jsonPath)
        delete(jsonPath);
    end
end

function rmpathIfPresent(pathText)
    pathParts = split(string(pathText), pathsep);
    activeParts = split(string(path), pathsep);
    removableParts = pathParts(ismember(lower(pathParts), lower(activeParts)));
    if ~isempty(removableParts)
        rmpath(char(join(removableParts, pathsep)));
    end
end

function restoreEnvironment(oldPath, oldFolder, oldFigureVisibility, runtimeRoot)
    path(oldPath);
    cd(oldFolder);
    set(groot, 'defaultFigureVisible', oldFigureVisibility);
    close all force;
    if isfolder(runtimeRoot)
        rmdir(runtimeRoot, 's');
    end
end
