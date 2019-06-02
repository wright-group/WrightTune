"""Function for processing multi-motor tuning data."""


import WrightTools as wt


__all__ = ["holistic"]


def holistic(OPA_index, data_filepath, curves, save=True):
    """Process preamp motortune.
    Parameters
    ----------
    opa_index : integer
        OPA index.
    data_filepath : string
        Data filepath.
    curves : list of strings
        Old curves.
    save : boolean (optional)
        Toggle saving. Default is True.
    Returns
    -------
    WrightTools.tuning.curve.Curve
    """
    # extract information from file
    headers = wt_kit.read_headers(data_filepath)
    arr = np.genfromtxt(data_filepath).T
    old_curve = wt_curve.from_TOPAS_crvs(curves, 'TOPAS-C', 'NON-NON-NON-Sig')
    # get array data
    array_colors = arr[headers['name'].index('wa')]
    array_data = arr[headers['name'].index('array_signal')]
    array_colors.shape = (-1, 256)
    array_data.shape = (-1, 256)
    array_colors = wt_units.converter(array_colors, 'nm', 'wn')
    # fit array data
    outs = []
    for i in range(len(array_data)):
        xi = array_colors[i]
        yi = array_data[i]
        function = wt_fit.Gaussian()
        mean, width, amplitude, baseline = function.fit(yi, xi)
        mean = wt_units.converter(mean, 'wn', 'nm')
        outs.append([amplitude, mean, width])
    outs = np.array(outs).T
    amps, centers, widths = outs
    # get crystal 1 data
    array_c1 = arr[headers['name'].index('w{}_Crystal_1'.format(OPA_index))]
    array_c1.shape = (-1, 256)
    c1_list = array_c1[..., 0].flatten()
    # get delay 1 data
    array_d1 = arr[headers['name'].index('w{}_Delay_1'.format(OPA_index))]
    array_d1.shape = (-1, 256)
    d1_list = array_d1[..., 0].flatten()
    d1_width = (array_d1[:, 0].max() - array_d1[:, 0].min()) / 2.
    # remove points with amplitudes that are ridiculous
    amps[amps < 0.1] = np.nan
    amps[amps > 4] = np.nan
    # remove points with centers that are ridiculous
    centers[centers < 1150] = np.nan
    centers[centers > 1650] = np.nan
    # remove points with widths that are ridiculous
    widths[widths < 5] = np.nan
    widths[widths > 500] = np.nan
    # finish removal
    amps, centers, widths, c1_list, d1_list = wt_kit.remove_nans_1D(
        [amps, centers, widths, c1_list, d1_list])
    # grid data (onto a fine grid)
    points_count = 100
    c1_points = np.linspace(c1_list.min(), c1_list.max(), points_count)
    d1_points = np.linspace(d1_list.min(), d1_list.max(), points_count)
    xi = tuple(np.meshgrid(c1_points, d1_points, indexing='xy'))
    c1_grid, d1_grid = xi
    points = tuple([c1_list, d1_list])
    amp_grid = griddata(points, amps, xi)
    cen_grid = griddata(points, centers, xi)
    # get indicies with centers near setpoints (bin data)
    setpoints = np.linspace(1140, 1620, 25)
    within = 2
    fits_by_setpoint = []
    print('binning points')
    for i in range(len(setpoints)):
        these_fits = []
        for j in range(points_count):
            for k in range(points_count):
                if np.isnan(amp_grid[k, j]):
                    pass
                else:
                    if np.abs(cen_grid[k, j] - setpoints[i]) < within:
                        motor_positions = [c1_grid[0, j], d1_grid[k, 0]]
                        amplitude = amp_grid[k, j]
                        these_fits.append([motor_positions, amplitude])
                    else:
                        pass
        if len(these_fits) > 0:
            max_amplitude = max([f[1] for f in these_fits])
            these_fits = [f for f in these_fits if f[1] > max_amplitude * 0.25]
        fits_by_setpoint.append(these_fits)
        wt_kit.update_progress(100 * i / float(len(setpoints)))
    wt_kit.update_progress(100)
    false_setpoints = []
    for i in range(len(setpoints)):
        if len(fits_by_setpoint[i]) == 0:
            false_setpoints.append(setpoints[i])
    # fit each setpoint
    preamp_chosen = []
    print('fitting points')
    for i in range(len(setpoints)):
        c1s = np.zeros(len(fits_by_setpoint[i]))
        d1s = np.zeros(len(fits_by_setpoint[i]))
        y = np.zeros(len(fits_by_setpoint[i]))
        chosen = np.zeros(3)  # color, c1, d1
        if len(y) == 0:
            continue
        for j in range(len(fits_by_setpoint[i])):
            c1s[j] = fits_by_setpoint[i][j][0][0]
            d1s[j] = fits_by_setpoint[i][j][0][1]
            y[j] = fits_by_setpoint[i][j][1]
        if len(y) < 4:
            # choose by expectation value if you don't have many points (failsafe)
            chosen[0] = setpoints[i]
            chosen[1] = _exp_value(y, c1s)
            chosen[2] = _exp_value(y, d1s)
        else:
            # fit to a guassian
            # c1
            amplitude_guess = max(y)
            center_guess = old_curve.get_motor_positions(setpoints[i])[0]
            sigma_guess = 100.
            p0 = np.array([amplitude_guess, center_guess, sigma_guess])
            try:
                out_c1 = leastsq(_gauss_residuals, p0, args=(y, c1s))[0]
            except RuntimeWarning:
                print('runtime')
            # d1
            amplitude_guess = max(y)
            center_guess = old_curve.get_motor_positions(setpoints[i])[1]
            sigma_guess = 100.
            p0 = np.array([amplitude_guess, center_guess, sigma_guess])
            try:
                out_d1 = leastsq(_gauss_residuals, p0, args=(y, d1s))[0]
            except RuntimeWarning:
                print('runtime')
            # write to preamp_chosen
            chosen[0] = setpoints[i]
            chosen[1] = out_c1[1]
            chosen[2] = out_d1[1]
        if chosen[1] < c1s.min() or chosen[1] > c1s.max():
            chosen[0] = setpoints[i]
            chosen[1] = _exp_value(y, c1s)
            chosen[2] = _exp_value(y, d1s)
        elif chosen[2] < d1s.min() or chosen[2] > d1s.max():
            chosen[0] = setpoints[i]
            chosen[1] = _exp_value(y, c1s)
            chosen[2] = _exp_value(y, d1s)
        else:
            pass
        preamp_chosen.append(chosen)
        wt_kit.update_progress(100 * i / float(len(setpoints)))
    wt_kit.update_progress(100)
    colors_chosen = [pc[0] for pc in preamp_chosen]
    c1s_chosen = [pc[1] for pc in preamp_chosen]
    d1s_chosen = [pc[2] for pc in preamp_chosen]
    # extend curve using spline
    if True:
        c1_spline = UnivariateSpline(colors_chosen, c1s_chosen, k=2, s=1000)
        d1_spline = UnivariateSpline(colors_chosen, d1s_chosen, k=2, s=1000)
        preamp_chosen = np.zeros([len(setpoints), 3])
        for i in range(len(setpoints)):
            preamp_chosen[i][0] = setpoints[i]
            preamp_chosen[i][1] = c1_spline(setpoints[i])
            preamp_chosen[i][2] = d1_spline(setpoints[i])
        false_points = np.zeros([len(false_setpoints), 3])
        for i in range(len(false_setpoints)):
            false_points[i][0] = false_setpoints[i]
            false_points[i][1] = c1_spline(false_setpoints[i])
            false_points[i][2] = d1_spline(false_setpoints[i])
    # create new curve
    colors = np.array([pc[0] for pc in preamp_chosen])
    motors = []
    old_curve_copy = old_curve.copy()
    old_curve_copy.map_colors(colors)
    for i, name in zip(range(1, 3), ['Crystal_1', 'Delay_1']):
        motors.append(wt_curve.Motor([pc[i] for pc in preamp_chosen], name))
    for i in range(2, 4):
        motors.append(old_curve_copy.motors[i])
    curve = old_curve.copy()
    curve.colors = colors
    curve.motors = motors
    curve.map_colors(setpoints)
    # preapre for plot
    fig, gs = wt_artists.create_figure(width='single', cols=[1, 'cbar'])
    cmap = wt_artists.colormaps['default']
    cmap.set_bad([0.75] * 3, 1.)
    cmap.set_under([0.75] * 3, 1.)
    # plot amplitude data
    ax = plt.subplot(gs[0, 0])
    X, Y, Z = wt_artists.pcolor_helper(c1_points, d1_points, amp_grid)
    mappable = ax.pcolor(X, Y, Z, vmin=0, vmax=np.nanmax(Z), cmap=cmap)
    # plot and label contours of constant color
    CS = plt.contour(c1_points, d1_points, cen_grid, colors='grey', levels=setpoints)
    clabel_positions = np.zeros([len(preamp_chosen), 2])
    clabel_positions[:, 0] = preamp_chosen[:, 1]
    clabel_positions[:, 1] = preamp_chosen[:, 2]
    plt.clabel(CS, inline=0, fontsize=9, manual=clabel_positions, colors='w', fmt='%1.0f')
    # plot old points, edges of acquisition
    xi = old_curve.motors[0].positions
    yi = old_curve.motors[1].positions
    plt.plot(xi, yi, c='k')
    plt.plot(xi, yi + d1_width, c='k', ls='--')
    plt.plot(xi, yi - d1_width, c='k', ls='--')
    for x, y in zip([xi[0], xi[-1]], [yi[0], yi[-1]]):
        xs = [x, x]
        ys = [y - d1_width, y + d1_width]
        plt.plot(xs, ys, c='k', ls='--')
    # plot points chosen by fits
    xi = [pc[1] for pc in preamp_chosen]
    yi = [pc[2] for pc in preamp_chosen]
    plt.plot(xi, yi, c='grey', lw=5)
    # plot smoothed points
    xi = curve.motors[0].positions
    yi = curve.motors[1].positions
    plt.plot(xi, yi, c='k', lw=5)
    # finish plot
    plt.xlabel('C1 (deg)', fontsize=18)
    plt.ylabel('D1 (mm)', fontsize=18)
    title = os.path.basename(data_filepath)
    plt.suptitle(title)
    plt.gca().patch.set_facecolor([0.75] * 3)
    plt.xlim(xi.min() - 0.25, xi.max() + 0.25)
    plt.ylim(yi.min() - 0.05, yi.max() + 0.05)
    # colorbar
    cax = plt.subplot(gs[:, -1])
    plt.colorbar(mappable=mappable, cax=cax)
    cax.set_ylabel('intensity', fontsize=18)
    # plot at an index (for debugging purposes only)
    # TODO: remove this eventually...
    if False:
        setpoint_index = 20
        fig2 = plt.figure()
        for i in range(len(fits_by_setpoint[setpoint_index])):
            c1_point = fits_by_setpoint[setpoint_index][i][0][0]
            d1_point = fits_by_setpoint[setpoint_index][i][0][1]
            amp = fits_by_setpoint[setpoint_index][i][1]
            fig.gca().scatter(c1_point, d1_point)
            fig2.gca().scatter(c1_point, amp)
            plt.title('c1 vs amp - {} nm'.format(setpoints[setpoint_index]))
        plt.show()
    # write files
    if save:
        directory = os.path.dirname(data_filepath)
        curve.save(save_directory=directory)
        image_path = data_filepath.replace('.data', '.png')
        # TODO: figure out how to get transparent background >:-(
        plt.savefig(image_path, dpi=300, transparent=False)
        plt.close(fig)
    # finish
    return curve
